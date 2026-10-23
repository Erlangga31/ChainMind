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
    sap_backend: Literal["mock", "sandbox", "real"] | None = None
    llm_backend: Literal["mock", "bedrock", "bedrock_agents"] | None = None
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_agent_id: str | None = None
    bedrock_agent_alias_id: str | None = None
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
    sap_integration_suite_url: str | None = None
    sap_token_url: str | None = None
    sap_client_id: str | None = None
    sap_client_secret: str | None = None
    sap_secrets_secret_id: str | None = None
    sap_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    sap_workflow_base_url: str = "http://127.0.0.1:8100"

    @property
    def resolved_sap_backend(self) -> Literal["mock", "sandbox", "real"]:
        """Resolve explicit SAP selection or the legacy overall mode preset."""

        return self.sap_backend or ("mock" if self.mode == "mock" else "real")

    @property
    def resolved_llm_backend(self) -> Literal["mock", "bedrock", "bedrock_agents"]:
        """Resolve explicit language-model selection or the legacy overall mode preset."""

        return self.llm_backend or ("mock" if self.mode == "mock" else "bedrock")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
