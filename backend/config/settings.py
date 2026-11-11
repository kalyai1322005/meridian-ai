"""All configuration in one place, read from environment variables / .env.

THE LOCAL <-> CLOUD TOGGLE
--------------------------
    APP_MODE=local   (default)  Runs on your laptop with ONLY a Gemini API key.
                                Vectors  -> Chroma, saved in ./.meridian/chroma
                                Files    -> ./.meridian/uploads
                                Embeddings -> Gemini API (API key)
                                No Google Cloud project, bucket or service account needed.

    APP_MODE=cloud              Runs on AWS (what ECS Fargate uses).
                                Vectors  -> Amazon OpenSearch Serverless
                                Files    -> Amazon S3
                                Models   -> Amazon Bedrock

Every module that touches storage asks `settings.is_cloud` instead of guessing,
so switching mode is one line in .env.
"""
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels above backend/config/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "Meridian AI - Procurement Intelligence"
    app_env: str = Field("local", validation_alias="ENVIRONMENT")
    app_version: str = "1.1.0"

    # --- The toggle ---
    app_mode: Literal["local", "cloud"] = Field("local", validation_alias="APP_MODE")

    # --- Local models (APP_MODE=local) ---
    GOOGLE_API_KEY: str = Field("", validation_alias="GOOGLE_API_KEY")
    local_llm_model_name: str = Field("gemini-3.8-flash", validation_alias="LOCAL_LLM_MODEL_NAME")
    llm_temperature: float = Field(0.0, validation_alias="LLM_TEMPERATURE")

    # --- Embeddings ---
    # AWS Titan Text Embeddings v2 defaults to 1,024 dimensions.
    embedding_model_name: str = Field("amazon.titan-embed-text-v2:0", validation_alias="BEDROCK_EMBEDDING_MODEL_ID")
    local_embedding_model_name: str = Field("gemini-embedding-001", validation_alias="LOCAL_EMBEDDING_MODEL_NAME")
    embedding_dimensions: int = Field(1024, validation_alias="EMBEDDING_DIMENSIONS")
    local_embedding_dimensions: int = 768

    # --- Local mode storage ---
    local_data_dir: str = Field(str(PROJECT_ROOT / ".meridian"), validation_alias="LOCAL_DATA_DIR")
    chroma_collection: str = Field("meridian_docs", validation_alias="CHROMA_COLLECTION")

    # --- AWS cloud mode ---
    aws_region: str = Field("us-east-1", validation_alias="AWS_REGION")
    s3_bucket_name: str = Field("", validation_alias="S3_BUCKET_NAME")
    s3_prefix: str = Field("uploads/", validation_alias="S3_PREFIX")
    opensearch_url: str = Field("", validation_alias="OPENSEARCH_URL")
    opensearch_index: str = Field("meridian-docs", validation_alias="OPENSEARCH_INDEX")
    bedrock_llm_model_id: str = Field("us.amazon.nova-lite-v1:0", validation_alias="BEDROCK_LLM_MODEL_ID")

    # --- Agent middleware limits ---
    agent_max_model_calls: int = Field(8, validation_alias="AGENT_MAX_MODEL_CALLS")
    agent_max_tool_calls: int = Field(6, validation_alias="AGENT_MAX_TOOL_CALLS")
    agent_max_retries: int = Field(2, validation_alias="AGENT_MAX_RETRIES")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),  # found no matter which folder you start from
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _normalise(self) -> "Settings":
        if self.s3_prefix and not self.s3_prefix.endswith("/"):
            self.s3_prefix += "/"
        return self

    # --- Convenience ---
    @property
    def is_cloud(self) -> bool:
        return self.app_mode == "cloud"

    @property
    def chroma_dir(self) -> str:
        return os.path.join(self.local_data_dir, "chroma")

    @property
    def local_upload_dir(self) -> str:
        return os.path.join(self.local_data_dir, "uploads")

    def missing_cloud_settings(self) -> list[str]:
        """Names of cloud settings that are still empty (used for clear error messages)."""
        required = {
            "S3_BUCKET_NAME": self.s3_bucket_name,
            "OPENSEARCH_URL": self.opensearch_url,
        }
        return [name for name, value in required.items() if not value]


settings = Settings()


