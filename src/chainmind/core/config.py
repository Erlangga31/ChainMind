"""Environment-backed application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the API, workflow, and infrastructure adapters."""

    model_config = SettingsConfigDict(
        env_prefix="CHAINMIND_",
        env_file=".env",
        extra="ignore",
    )

    mode: Literal["mock", "aws"] = "mock"
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    stockout_tolerance_days: float = Field(default=0.0, ge=0)
    safety_reserve_days: float = Field(default=0.25, ge=0)
    retry_attempts: int = Field(default=3, ge=1, le=8)
    retry_base_delay_seconds: float = Field(default=0.1, ge=0)
    event_table_name: str = "chainmind-events"
    artifact_bucket_name: str = "chainmind-artifacts"
    api_cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    sap_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
