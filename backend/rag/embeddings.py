"""Text -> vector conversion, used both when indexing documents and when searching.

The SAME model must be used for indexing and for querying, so the model follows APP_MODE:

    local  -> gemini-embedding-001 through the Gemini API (only GOOGLE_API_KEY needed)
    cloud  -> Amazon Titan Text Embeddings v2 through Amazon Bedrock (AWS IAM)

The default Bedrock model produces 1,024-dimensional vectors in cloud mode.

The Gemini integration is used only by local mode; AWS cloud mode initializes the
Bedrock integration on first use.
"""
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config.settings import settings
from exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    if settings.is_cloud:
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(model_id=settings.embedding_model_name, region_name=settings.aws_region)

    if not settings.GOOGLE_API_KEY:
        raise ConfigurationError("APP_MODE=local needs GOOGLE_API_KEY in .env for embeddings.")
    return GoogleGenerativeAIEmbeddings(
        model=settings.local_embedding_model_name,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=settings.local_embedding_dimensions,
    )
