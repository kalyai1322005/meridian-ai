"""The LLM used by both the RAG chain and the agents.

Two providers, chosen with LLM_PROVIDER:

  gemini  (default) Gemini API with an API key (GOOGLE_API_KEY), in BOTH modes:
            * local - the key comes from your .env
            * cloud - ECS injects the same key from AWS Secrets Manager
  bedrock           Amazon Bedrock through the Converse API. No API key: AWS credentials
                    are used (the ECS task role in the cloud). Set BEDROCK_LLM_MODEL_ID.

Embeddings (rag/embeddings.py) follow APP_MODE, not this setting.
"""
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import settings
from exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Create the chat model on first use (not at import time) and reuse it afterwards."""
    if settings.llm_provider == "bedrock":
        if not settings.bedrock_llm_model_id:
            raise ConfigurationError(
                "LLM_PROVIDER=bedrock needs BEDROCK_LLM_MODEL_ID (a model or inference-profile ID you can use in Bedrock)."
            )
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=settings.bedrock_llm_model_id,
            region_name=settings.AWS_REGION,
            temperature=settings.llm_temperature,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.GOOGLE_API_KEY:
        raise ConfigurationError("GOOGLE_API_KEY is empty. Add it to .env (https://aistudio.google.com/apikey).")
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_name,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.llm_temperature,
    )


def extract_text(content) -> str:
    """Models may return a list of content blocks, e.g. [{'type': 'text', 'text': '...'}]; join the text."""
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return content
