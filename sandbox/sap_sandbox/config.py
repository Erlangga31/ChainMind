"""Environment-backed settings for the local SAP sandbox."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    """Settings for local webhook delivery from sandbox simulators."""

    model_config = SettingsConfigDict(
        env_prefix="SAP_SANDBOX_",
        env_file=".env",
        extra="ignore",
    )

    event_webhook_url: str = "http://127.0.0.1:8000/disruptions"
    workflow_callback_url: str = "http://127.0.0.1:8000"


@lru_cache
def get_sandbox_settings() -> SandboxSettings:
    """Return the process-wide SAP sandbox settings."""

    return SandboxSettings()
