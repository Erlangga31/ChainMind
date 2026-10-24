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

    event_webhook_url: str = "http://127.0.0.1:8000/event-bridge"
    event_bridge_secret: str | None = None
    workflow_callback_url: str = "http://127.0.0.1:8000"
    oidc_issuer: str = "http://127.0.0.1:8100"
    oidc_audience: str = "chainmind-dashboard"
    oidc_client_id: str = "chainmind-dashboard"
    oidc_redirect_uri: str = "http://localhost:5173/"


@lru_cache
def get_sandbox_settings() -> SandboxSettings:
    """Return the process-wide SAP sandbox settings."""

    return SandboxSettings()
