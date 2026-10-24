"""Deterministic tenant metering and illustrative plan estimates."""

from datetime import UTC, datetime, time

from chainmind.core.config import Settings
from chainmind.core.models import DisruptionRun, RunStatus, UsageReport


def calculate_usage(
    tenant_id: str,
    runs: list[DisruptionRun],
    settings: Settings,
    as_of: datetime | None = None,
) -> UsageReport:
    """Calculate current-month tenant usage and an illustrative invoice estimate."""

    current_time = as_of or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("Usage calculation time must include a timezone.")
    current_time = current_time.astimezone(UTC)
    period_start = current_time.date().replace(day=1)
    period_start_timestamp = datetime.combine(period_start, time.min, tzinfo=UTC)
    plan_tier = settings.usage_tenant_plan_tiers.get(tenant_id, settings.usage_plan_tier)
    plan = settings.usage_pricing_tiers.get(plan_tier)
    if plan is None:
        raise ValueError(f"No pricing configuration exists for {plan_tier}.")

    tenant_runs = [run for run in runs if run.tenant_id == tenant_id]
    resolved = sum(
        run.status == RunStatus.EXECUTED and run.updated_at >= period_start_timestamp
        for run in tenant_runs
    )
    active_agents = settings.usage_tenant_active_agents.get(
        tenant_id,
        settings.usage_active_agents,
    )
    overage = max(resolved - plan.included_disruptions, 0) * plan.extra_disruption_fee
    additional_agents = max(active_agents - plan.included_agents, 0)
    agent_fee = additional_agents * plan.extra_agent_fee
    monthly = plan.monthly_fee + overage + agent_fee
    first_invoice = monthly + plan.onboarding_fee

    return UsageReport(
        tenant_id=tenant_id,
        period_start=period_start,
        plan_tier=plan_tier,
        resolved_disruptions=resolved,
        included_disruptions=plan.included_disruptions,
        active_agents=active_agents,
        included_agents=plan.included_agents,
        monthly_subscription_fee=plan.monthly_fee,
        disruption_overage_fee=overage,
        additional_agent_fee=agent_fee,
        one_time_onboarding_fee=plan.onboarding_fee,
        illustrative_monthly_estimate=monthly,
        illustrative_first_invoice_estimate=first_invoice,
    )
