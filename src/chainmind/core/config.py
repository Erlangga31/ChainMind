"""Environment-backed application configuration."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UsagePricingTier(BaseModel):
    """Illustrative metering prices configurable through ChainMind settings."""

    monthly_fee: float = Field(ge=0)
    included_disruptions: int = Field(ge=0)
    included_agents: int = Field(ge=0)
    extra_disruption_fee: float = Field(ge=0)
    extra_agent_fee: float = Field(ge=0)
    onboarding_fee: float = Field(ge=0)


def _default_usage_pricing() -> dict[str, UsagePricingTier]:
    return {
        "Starter": UsagePricingTier(
            monthly_fee=500,
            included_disruptions=10,
            included_agents=4,
            extra_disruption_fee=50,
            extra_agent_fee=100,
            onboarding_fee=1_000,
        ),
        "Professional": UsagePricingTier(
            monthly_fee=2_500,
            included_disruptions=100,
            included_agents=4,
            extra_disruption_fee=25,
            extra_agent_fee=75,
            onboarding_fee=5_000,
        ),
        "Enterprise": UsagePricingTier(
            monthly_fee=10_000,
            included_disruptions=1_000,
            included_agents=5,
            extra_disruption_fee=10,
            extra_agent_fee=50,
            onboarding_fee=15_000,
        ),
    }


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
    auth_issuer: str = "http://127.0.0.1:8100"
    auth_audience: str = "chainmind-dashboard"
    auth_jwks_url: str = "http://127.0.0.1:8100/.well-known/jwks.json"
    auth_dev_bypass: bool = False
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_agent_id: str | None = None
    bedrock_agent_alias_id: str | None = None
    stockout_tolerance_days: float = Field(default=0.0, ge=0)
    safety_reserve_days: float = Field(default=0.25, ge=0)
    retry_attempts: int = Field(default=3, ge=1, le=8)
    retry_base_delay_seconds: float = Field(default=0.1, ge=0)
    max_revisions: int = Field(default=3, ge=0, le=10)
    event_table_name: str = "chainmind-events"
    event_database_path: str = "data/chainmind-events.sqlite3"
    event_bus_name: str = "chainmind"
    event_bridge_secret: str | None = None
    notification_backends: list[Literal["console", "teams", "slack", "email"]] = Field(
        default_factory=lambda: ["console"]
    )
    notification_link_secret: str | None = None
    notification_link_secret_id: str | None = None
    notification_link_ttl_minutes: int = Field(default=60, ge=1, le=10_080)
    notification_api_base_url: str = "http://localhost:8000"
    notification_dashboard_url: str = "http://localhost:5173"
    notification_approval_overdue_minutes: int = Field(default=1_440, ge=1)
    notification_eta_deviation_threshold_days: float = Field(default=0, ge=0)
    notification_teams_webhook_url: str | None = None
    notification_slack_webhook_url: str | None = None
    notification_email_sender: str | None = None
    notification_email_recipient: str | None = None
    notification_email_outbox_path: str = "data/notifications.jsonl"
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
    usage_plan_tier: Literal["Starter", "Professional", "Enterprise"] = "Starter"
    usage_active_agents: int = Field(default=5, ge=0)
    usage_tenant_plan_tiers: dict[str, Literal["Starter", "Professional", "Enterprise"]] = Field(
        default_factory=dict
    )
    usage_tenant_active_agents: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    usage_pricing_tiers: dict[str, UsagePricingTier] = Field(default_factory=_default_usage_pricing)

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
