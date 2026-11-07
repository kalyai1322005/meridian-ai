"""Tests for the local/cloud toggle, the local RAG pipeline and the agent middleware.

Everything runs offline: embeddings and the chat model are replaced by fakes.
"""
import os
import pytest
from fastapi.testclient import TestClient
from langchain.agents import create_agent
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from agent.middleware import build_agent_middleware
from api.main import app
from config.settings import Settings, settings
from exceptions import ConfigurationError
from rag import retrieval, vector_store
from rag.data_ingestion import ingest_pdf, ingest_stored_pdfs

client = TestClient(app)


class FakeToolModel(GenericFakeChatModel):
    """A scripted chat model that 'supports' tools, so create_agent accepts it."""

    def bind_tools(self, tools, **kwargs):
        return self


# ---------------------------------------------------------------------------
# The toggle
# ---------------------------------------------------------------------------

def test_default_mode_is_local(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    assert Settings(_env_file=None).app_mode == "local"


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_MODE", "hybrid")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_cloud_mode_lists_missing_settings(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "cloud")
    vector_store.get_vector_store.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="S3_VECTORS_BUCKET_NAME"):
            vector_store.get_vector_store()
    finally:
        vector_store.get_vector_store.cache_clear()


def test_missing_api_key_gives_503_not_500(monkeypatch):
    from rag import llm

    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")
    llm.get_llm.cache_clear()
    try:
        res = client.post("/api/rag/ask", json={"query": "hi"})
        assert res.status_code == 503
        assert "GOOGLE_API_KEY" in res.json()["detail"]
    finally:
        llm.get_llm.cache_clear()


# ---------------------------------------------------------------------------
# Local RAG end to end: PDF -> Chroma -> retrieval -> answer
# ---------------------------------------------------------------------------

@pytest.fixture
def offline_local_store(monkeypatch):
    monkeypatch.setattr(vector_store, "get_embeddings", lambda: DeterministicFakeEmbedding(size=768))
    vector_store.get_vector_store.cache_clear()
    yield vector_store.get_vector_store()
    vector_store.get_vector_store.cache_clear()


def test_local_ingest_and_ask(offline_local_store, monkeypatch, tmp_path):
    import glob
    import os
    import shutil

    pdf = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "sample_docs", "*.pdf")))[0]
    summary = ingest_pdf(pdf, "local://sample.pdf")
    assert summary["chunks"] > 0

    # Re-ingesting the same file must not duplicate chunks (stable IDs)
    before = offline_local_store._collection.count()
    ingest_pdf(pdf, "local://sample.pdf")
    assert offline_local_store._collection.count() == before

    # The "Index stored documents" button reads from the local upload folder
    os.makedirs(settings.local_upload_dir, exist_ok=True)
    shutil.copy(pdf, settings.local_upload_dir)
    assert ingest_stored_pdfs()["files"] == 1

    fake_llm = GenericFakeChatModel(messages=iter([AIMessage(content="EUR 2.84 billion")]))
    monkeypatch.setattr(retrieval, "get_llm", lambda: fake_llm)
    assert retrieval.ask_question("What is the revenue?") == "EUR 2.84 billion"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def test_middleware_stack_has_the_expected_layers():
    names = [type(m).__name__ for m in build_agent_middleware()]
    for expected in ["PIIMiddleware", "ModelCallLimitMiddleware", "ToolCallLimitMiddleware",
                     "ModelRetryMiddleware", "ToolRetryMiddleware"]:
        assert expected in names


def test_agent_runs_tools_through_middleware_and_redacts_email():
    calls = []

    @tool
    def lookup_vendor(vendor_name: str) -> str:
        """Look a vendor up."""
        calls.append(vendor_name)
        return "CLEARED"

    model = FakeToolModel(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "lookup_vendor", "args": {"vendor_name": "Takumi"}, "id": "1"}]),
        AIMessage(content="SANCTIONS CHECK: CLEARED"),
    ]))
    agent = create_agent(model=model, tools=[lookup_vendor], middleware=build_agent_middleware())
    result = agent.invoke({"messages": [HumanMessage("Screen Takumi, contact buyer@aldermoor.example")]})

    assert calls == ["Takumi"]
    assert result["messages"][-1].text == "SANCTIONS CHECK: CLEARED"
    assert "buyer@aldermoor.example" not in result["messages"][0].text


def test_supervisor_builds_three_agents_with_middleware():
    from agent.agents import ProcurementSupervisor

    supervisor = ProcurementSupervisor()  # no network call happens at build time
    assert supervisor.risk_agent and supervisor.tax_agent and supervisor.control_agent


# ---------------------------------------------------------------------------
# Cloud mode (AWS): wiring only, no real AWS calls
# ---------------------------------------------------------------------------

def test_cloud_embeddings_use_bedrock_titan_with_configured_size(monkeypatch):
    from rag import embeddings

    monkeypatch.setattr(settings, "app_mode", "cloud")
    embeddings.get_embeddings.cache_clear()
    try:
        emb = embeddings.get_embeddings()
        assert type(emb).__name__ == "BedrockEmbeddings"
        assert emb.model_id == "amazon.titan-embed-text-v2:0"
        assert emb.dimensions == settings.cloud_embedding_dimensions == 1024
    finally:
        embeddings.get_embeddings.cache_clear()


def test_cloud_vector_store_is_s3_vectors_with_text_not_filterable(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "cloud")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "docs-bucket")
    monkeypatch.setattr(settings, "s3_vectors_bucket_name", "vectors-bucket")
    vector_store.get_vector_store.cache_clear()
    try:
        store = vector_store.get_vector_store()
        assert type(store).__name__ == "AmazonS3Vectors"
        assert store.vector_bucket_name == "vectors-bucket"
        assert store.index_name == settings.s3_vectors_index_name
        assert store.non_filterable_metadata_keys == ["_page_content"]
    finally:
        vector_store.get_vector_store.cache_clear()


def test_bedrock_llm_provider_needs_a_model_id(monkeypatch):
    from rag import llm

    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "bedrock_llm_model_id", "")
    llm.get_llm.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="BEDROCK_LLM_MODEL_ID"):
            llm.get_llm()
    finally:
        llm.get_llm.cache_clear()


def test_old_vertex_llm_setting_name_still_works(monkeypatch):
    monkeypatch.setenv("VERTEX_LLM_MODEL_NAME", "gemini-old-name")
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    assert Settings(_env_file=None).llm_model_name == "gemini-old-name"


def test_s3_document_store_round_trip(monkeypatch, tmp_path):
    """PDFs saved in cloud mode land in S3 under the prefix and are listed back for indexing."""
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    from rag import document_store

    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docs-bucket")
        monkeypatch.setattr(settings, "app_mode", "cloud")
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", "docs-bucket")
        monkeypatch.setattr(settings, "S3_PREFIX", "uploads/")

        pdf = tmp_path / "invoice.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "notes.txt").write_text("ignored")

        assert document_store.save(str(pdf), "invoice.pdf") == "s3://docs-bucket/uploads/invoice.pdf"
        boto3.client("s3", region_name="us-east-1").put_object(Bucket="docs-bucket", Key="uploads/notes.txt", Body=b"x")

        with document_store.pdfs() as files:
            found = [(os.path.basename(path), source) for path, source in files]
        assert found == [("invoice.pdf", "s3://docs-bucket/uploads/invoice.pdf")]
        assert document_store.location() == "s3://docs-bucket/uploads/"


def test_logs_are_flushed_to_s3_in_cloud_mode(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    from logger.custom_logger import CustomLogger

    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docs-bucket")
        monkeypatch.setattr(settings, "app_mode", "cloud")
        monkeypatch.setattr(settings, "S3_BUCKET_NAME", "docs-bucket")

        custom = CustomLogger(log_dir="test_logs_s3")
        with open(custom.log_file_path, "w") as fh:
            fh.write('{"event": "x"}\n')
        custom.flush_to_s3()

        keys = [o["Key"] for o in boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="docs-bucket")["Contents"]]
        assert keys == [f"logs/{custom._timestamp}.log"]
