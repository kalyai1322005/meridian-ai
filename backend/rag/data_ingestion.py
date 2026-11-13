"""Getting documents INTO the vector database.

    PDF file -> pages -> chunks (~1000 characters) -> embeddings -> vector store

Two entry points share the same steps:
  * ingest_pdf()          - one PDF on disk (used by the upload endpoint)
  * ingest_stored_pdfs()  - every PDF in the document store
                            (local: .meridian/uploads/, cloud: the S3 bucket)
"""
import hashlib
import re
import time

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from exceptions import IngestionError
from logger import GLOBAL_LOGGER as log
from rag import document_store
from rag.vector_store import get_vector_store

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100  # neighbouring chunks share 100 characters so sentences are not cut off

# The free Gemini tier allows ~100 embedding requests per minute (one per chunk).
# We send chunks in small batches, pause between batches, and retry when Google says "slow down".
BATCH_SIZE = 60
PAUSE_BETWEEN_BATCHES = 40  # seconds
MAX_RETRIES = 6


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def _retry_delay(exc: Exception) -> float:
    """Use Google's 'Please retry in 10.0s' hint when present, else wait a minute."""
    match = re.search(r"retry in ([0-9.]+)s", str(exc))
    return float(match.group(1)) + 2 if match else 60.0


def _add_in_batches(chunks: list[Document], ids: list[str], source: str) -> None:
    store = get_vector_store()
    total = len(chunks)
    for start in range(0, total, BATCH_SIZE):
        batch, batch_ids = chunks[start:start + BATCH_SIZE], ids[start:start + BATCH_SIZE]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                store.add_documents(batch, ids=batch_ids)
                break
            except Exception as exc:  # noqa: BLE001 - only rate limits are retried
                if not _is_rate_limit(exc) or attempt == MAX_RETRIES:
                    raise
                delay = _retry_delay(exc)
                log.warning("Embedding rate limit hit, waiting", source=source, seconds=delay, attempt=attempt)
                time.sleep(delay)
        done = min(start + BATCH_SIZE, total)
        log.info("Embedded batch", source=source, done=done, total=total)
        if done < total:
            time.sleep(PAUSE_BETWEEN_BATCHES)


def split_into_chunks(pages: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return splitter.split_documents(pages)


def _chunk_id(chunk: Document, position: int) -> str:
    """Stable ID per chunk: re-indexing the same file overwrites instead of duplicating."""
    key = f"{chunk.metadata.get('source')}|{chunk.metadata.get('page')}|{position}"
    return hashlib.sha1(key.encode()).hexdigest()


def ingest_pdf(local_path: str, source: str) -> dict:
    """Load one PDF, chunk it and store it. Returns {"pages": n, "chunks": n}.

    `source` is saved in each chunk's metadata so answers can be traced back to a file.
    """
    try:
        pages = PyPDFLoader(local_path).load()
    except Exception as exc:  # pypdf raises many different error types
        raise IngestionError(f"Could not read PDF '{source}': {exc}") from exc

    for page in pages:
        page.metadata["source"] = source

    chunks = split_into_chunks(pages)
    if chunks:
        log.info("Embedding chunks and adding to vector store", source=source, chunks=len(chunks))
        ids = [_chunk_id(c, i) for i, c in enumerate(chunks)]
        _add_in_batches(chunks, ids, source)
    return {"pages": len(pages), "chunks": len(chunks)}


def ingest_stored_pdfs() -> dict:
    """Index every PDF already in the document store."""
    log.info("Indexing stored documents", location=document_store.location())
    totals = {"files": 0, "pages": 0, "chunks": 0}

    with document_store.pdfs() as files:
        for local_path, source in files:
            result = ingest_pdf(local_path, source=source)
            log.info("Ingested stored PDF", source=source, **result)
            totals["files"] += 1
            totals["pages"] += result["pages"]
            totals["chunks"] += result["chunks"]

    if totals["files"] == 0:
        log.warning("No PDF documents found in the document store", location=document_store.location())
    log.info("Ingestion complete", **totals)
    return totals
