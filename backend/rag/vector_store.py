"""The vector database that stores our embeddings. Which one depends on APP_MODE.

    local  -> Chroma, a vector database that saves to a folder on your disk
    cloud  -> Amazon S3 Vectors, AWS's pay-per-use managed vector storage

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

    from langchain_aws.vectorstores.s3_vectors import AmazonS3Vectors

    log.info(
        "Using Amazon S3 Vectors",
        vector_bucket=settings.s3_vectors_bucket_name,
        index=settings.s3_vectors_index_name,
    )
    return AmazonS3Vectors(
        vector_bucket_name=settings.s3_vectors_bucket_name,
        index_name=settings.s3_vectors_index_name,
        embedding=get_embeddings(),
        region_name=settings.AWS_REGION,
        distance_metric="cosine",
        # The chunk text is stored next to each vector. It must be "non-filterable",
        # otherwise S3 Vectors rejects it for being over the 2 KB filterable-metadata limit.
        non_filterable_metadata_keys=["_page_content"],
        create_index_if_not_exist=True,  # safety net; the bootstrap stack normally creates the index
    )


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Connect on first use, so the API can start (e.g. /api/health) before anything is configured."""
    return _cloud_store() if settings.is_cloud else _local_store()
