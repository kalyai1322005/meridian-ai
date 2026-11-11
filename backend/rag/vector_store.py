"""The vector database that stores our embeddings. Which one depends on APP_MODE.

    local  -> Chroma, a vector database that saves to a folder on your disk
    cloud  -> Amazon OpenSearch Serverless vector collection

Both are LangChain `VectorStore`s, so the rest of the code (ingestion, retrieval)
calls the same methods (`add_documents`, `as_retriever`) and never knows which one it got.
"""
from functools import lru_cache

from langchain_core.vectorstores import VectorStore

from config.settings import settings
from exceptions import ConfigurationError
from logger import GLOBAL_LOGGER as log
from rag.embeddings import get_embeddings


def _local_store() -> VectorStore:
    from langchain_chroma import Chroma  # imported here so cloud images do not need it loaded

    log.info("Using local Chroma vector store", path=settings.chroma_dir)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_dir,
    )


def _cloud_store() -> VectorStore:
    missing = settings.missing_cloud_settings()
    if missing:
        raise ConfigurationError(f"APP_MODE=cloud but these settings are empty: {', '.join(missing)}")

    import boto3
    from opensearchpy import AWSV4SignerAuth, RequestsHttpConnection
    from langchain_community.vectorstores import OpenSearchVectorSearch

    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise ConfigurationError("AWS credentials were not found. On ECS, check the task role; locally, run aws configure or aws sso login.")
    auth = AWSV4SignerAuth(credentials, settings.aws_region, "aoss")
    log.info("Using Amazon OpenSearch Serverless", index=settings.opensearch_index)
    return OpenSearchVectorSearch(
        opensearch_url=settings.opensearch_url,
        index_name=settings.opensearch_index,
        embedding_function=get_embeddings(),
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        engine="faiss",
    )


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Connect on first use, so the API can start (e.g. /api/health) before anything is configured."""
    return _cloud_store() if settings.is_cloud else _local_store()
