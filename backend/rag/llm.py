"""The LLM used by both the RAG chain and the agents.

Local mode uses Gemini with GOOGLE_API_KEY. Cloud mode uses Amazon Bedrock with the
ECS task role, so no AWS access keys or Google API key are stored in the container.
"""
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import settings
from exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Create the chat model on first use (not at import time) and reuse it afterwards."""  # config reload marker
    if settings.is_cloud:
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=settings.bedrock_llm_model_id,
            region_name=settings.aws_region,
            temperature=settings.llm_temperature,
        )
    if not settings.GOOGLE_API_KEY:
        raise ConfigurationError("GOOGLE_API_KEY is empty. Add it to .env (https://aistudio.google.com/apikey).")
    return ChatGoogleGenerativeAI(
        model=settings.local_llm_model_name,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.llm_temperature,
    )


def extract_text(content) -> str:
    """Gemini may return a list of content blocks, e.g. [{'type': 'text', 'text': '...'}]; join the text."""
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return content
