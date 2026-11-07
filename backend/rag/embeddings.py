"""Text -> vector conversion, used both when indexing documents and when searching.

The SAME model must be used for indexing and for querying, so the model follows APP_MODE:

    local  -> gemini-embedding-001 through the Gemini API (only GOOGLE_API_KEY needed), 768 dims
    cloud  -> amazon.titan-embed-text-v2:0 through Amazon Bedrock (AWS credentials), 1024 dims

In cloud mode the dimension number is fixed by the S3 Vectors index when it is created
(see infra/aws-bootstrap.yaml). Changing the model or the size later means a new index.
"""
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from config.settings import settings
from exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    if settings.is_cloud:
        from langchain_aws import BedrockEmbeddings  # imported here so local mode never needs AWS

        return BedrockEmbeddings(
            model_id=settings.embedding_model_name,
            region_name=settings.AWS_REGION,
            dimensions=settings.cloud_embedding_dimensions,
            normalize=True,
        )

    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    if not settings.GOOGLE_API_KEY:
        raise ConfigurationError("APP_MODE=local needs GOOGLE_API_KEY in .env for embeddings.")
    return GoogleGenerativeAIEmbeddings(
        model=settings.local_embedding_model_name,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=settings.embedding_dimensions,
    )
