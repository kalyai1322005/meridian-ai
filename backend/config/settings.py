"""All configuration in one place, read from environment variables / .env.

THE LOCAL <-> CLOUD TOGGLE
--------------------------
    APP_MODE=local   (default)  Runs on your laptop with ONLY a Gemini API key.
                                Vectors  -> Chroma, saved in ./.meridian/chroma
                                Files    -> ./.meridian/uploads
                                Embeddings -> Gemini API (API key)
                                No AWS account, bucket or credentials needed.

    APP_MODE=cloud              Runs against AWS (what ECS Express Mode uses).
                                Vectors  -> Amazon S3 Vectors
                                Files    -> Amazon S3 bucket
                                Embeddings -> Amazon Bedrock (Titan Text Embeddings V2)

Every module that touches storage asks `settings.is_cloud` instead of guessing,
so switching mode is one line in .env.
"""
import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
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

    # --- Chat model ---
    # "gemini" (default): Gemini API with GOOGLE_API_KEY, works in BOTH modes.
    # "bedrock": Amazon Bedrock (Converse API) using AWS credentials, set BEDROCK_LLM_MODEL_ID.
    llm_provider: Literal["gemini", "bedrock"] = Field("gemini", validation_alias="LLM_PROVIDER")
    GOOGLE_API_KEY: str = Field("", validation_alias="GOOGLE_API_KEY")
    # VERTEX_LLM_MODEL_NAME is the old name of this setting; it still works.
    llm_model_name: str = Field(
        "gemini-3.8-flash", validation_alias=AliasChoices("LLM_MODEL_NAME", "VERTEX_LLM_MODEL_NAME")
    )
    bedrock_llm_model_id: str = Field("", validation_alias="BEDROCK_LLM_MODEL_ID")
    # 0 = most repeatable answers. If the model loops or repeats itself, try 1.0 (Gemini 3 default)
    llm_temperature: float = Field(0.0, validation_alias="LLM_TEMPERATURE")

    # --- Embeddings ---
    # Cloud: Amazon Titan Text Embeddings V2 on Bedrock (supports 256, 512 or 1024 dimensions).
    # The S3 Vectors index is created with this size and can never change afterwards.
    embedding_model_name: str = Field(
        "amazon.titan-embed-text-v2:0", validation_alias=AliasChoices("BEDROCK_EMBEDDING_MODEL_ID", "EMBEDDING_MODEL_NAME")
    )
    cloud_embedding_dimensions: int = Field(1024, validation_alias="BEDROCK_EMBEDDING_DIMENSIONS")
    # Local: Gemini API model (API key). Chroma has no fixed size.
    local_embedding_model_name: str = Field("gemini-embedding-001", validation_alias="LOCAL_EMBEDDING_MODEL_NAME")
    embedding_dimensions: int = 768

    # --- Local mode storage ---
    local_data_dir: str = Field(str(PROJECT_ROOT / ".meridian"), validation_alias="LOCAL_DATA_DIR")
    chroma_collection: str = Field("meridian_docs", validation_alias="CHROMA_COLLECTION")

    # --- Cloud mode (AWS) ---
    # Credentials are NOT settings: boto3 finds them itself (the ECS task role in the cloud,
    # AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY on a laptop).
    AWS_REGION: str = Field("us-east-1", validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"))
    S3_BUCKET_NAME: str = Field("", validation_alias="S3_BUCKET_NAME")          # original PDFs + logs
    S3_PREFIX: str = Field("uploads/", validation_alias="S3_PREFIX")
    s3_vectors_bucket_name: str = Field("", validation_alias="S3_VECTORS_BUCKET_NAME")
    s3_vectors_index_name: str = Field("meridian-docs", validation_alias="S3_VECTORS_INDEX_NAME")

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
        # Keep the S3 prefix in the form "uploads/" so keys are built the same way everywhere
        if self.S3_PREFIX and not self.S3_PREFIX.endswith("/"):
            self.S3_PREFIX += "/"
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
            "S3_BUCKET_NAME": self.S3_BUCKET_NAME,
            "S3_VECTORS_BUCKET_NAME": self.s3_vectors_bucket_name,
            "S3_VECTORS_INDEX_NAME": self.s3_vectors_index_name,
        }
        return [name for name, value in required.items() if not value]


settings = Settings()
