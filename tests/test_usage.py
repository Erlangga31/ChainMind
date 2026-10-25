from datetime import UTC, date, datetime, timedelta

import pytest

from chainmind.core.config import Settings
from chainmind.core.models import DisruptionEvent, DisruptionRun, RunStatus
from chainmind.core.usage import calculate_usage


def test_usage_meter_counts_only_tenant_resolutions_and_reports_invoice_lines() -> None:
    runs = [
        DisruptionRun(
            event=DisruptionEvent(
                title=f"Disruption {index}",
                description="A qualifying tenant disruption.",
                delay_days=1,
                idempotency_key=f"event-{index}",
            ),
            tenant_id="tenant-a",
            status=RunStatus.EXECUTED,
        )
        for index in range(12)
    ]
    runs.append(
        DisruptionRun(
            event=DisruptionEvent(
                title="Other tenant",
                description="Must not count.",
                delay_days=1,
                idempotency_key="other",
            ),
            tenant_id="tenant-b",
            status=RunStatus.EXECUTED,
        )
    )
    settings = Settings(
        usage_plan_tier="Starter",
        usage_active_agents=5,
    )

    report = calculate_usage("tenant-a", runs, settings)

    assert report.resolved_disruptions == 12
    assert report.active_agents == 5
    assert report.disruption_overage_fee == 100
    assert report.additional_agent_fee == 100
    assert report.one_time_onboarding_fee == 1_000
    assert report.illustrative_monthly_estimate == 700
    assert report.illustrative_first_invoice_estimate == 1_700
    assert report.illustrative is True


def test_usage_counts_only_executed_disruptions() -> None:
    run = DisruptionRun(
        tenant_id="tenant-a",
        event=DisruptionEvent(
            title="Pending",
            description="This run is not resolved yet.",
            delay_days=1,
        ),
        status=RunStatus.PENDING_APPROVAL,
    )

    report = calculate_usage("tenant-a", [run], Settings())

    assert report.resolved_disruptions == 0


def test_usage_is_monthly_and_uses_tenant_plan_and_agent_configuration() -> None:
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    current_month = DisruptionRun(
        tenant_id="tenant-a",
        event=DisruptionEvent(
            title="Current month",
            description="Counts in the current billing period.",
            delay_days=1,
        ),
        status=RunStatus.EXECUTED,
        updated_at=now,
    )
    previous_month = DisruptionRun(
        tenant_id="tenant-a",
        event=DisruptionEvent(
            title="Previous month",
            description="Does not count in the current billing period.",
            delay_days=1,
        ),
        status=RunStatus.EXECUTED,
        updated_at=datetime(2026, 10, 1, tzinfo=UTC) - timedelta(seconds=1),
    )
    settings = Settings(
        usage_plan_tier="Starter",
        usage_active_agents=5,
        usage_tenant_plan_tiers={"tenant-a": "Professional"},
        usage_tenant_active_agents={"tenant-a": 3},
    )

    report = calculate_usage(
        "tenant-a",
        [current_month, previous_month],
        settings,
        as_of=now,
    )

    assert report.period_start == date(2026, 10, 1)
    assert report.plan_tier == "Professional"
    assert report.resolved_disruptions == 1
    assert report.active_agents == 3
    assert report.illustrative_monthly_estimate == 2_500


def test_usage_pricing_and_tenant_overrides_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAINMIND_USAGE_PLAN_TIER", "Professional")
    monkeypatch.setenv("CHAINMIND_USAGE_TENANT_PLAN_TIERS", '{"tenant-a":"Enterprise"}')
    monkeypatch.setenv("CHAINMIND_USAGE_TENANT_ACTIVE_AGENTS", '{"tenant-a":2}')
    monkeypatch.setenv(
        "CHAINMIND_USAGE_PRICING_TIERS",
        '{"Enterprise":{"monthly_fee":1234,"included_disruptions":20,"included_agents":3,'
        '"extra_disruption_fee":8,"extra_agent_fee":9,"onboarding_fee":456}}',
    )

    settings = Settings(_env_file=None)

    assert settings.usage_plan_tier == "Professional"
    assert settings.usage_tenant_plan_tiers["tenant-a"] == "Enterprise"
    assert settings.usage_tenant_active_agents["tenant-a"] == 2
    assert settings.usage_pricing_tiers["Enterprise"].monthly_fee == 1_234
