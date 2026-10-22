"""Focused unit tests for severity, coverage, and vendor economics."""

from chainmind.agents.logistics import calculate_coverage_days
from chainmind.agents.monitoring import MonitoringAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.config import Settings
from chainmind.core.models import DisruptionEvent, LogisticsResult, Severity
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient


def test_coverage_uses_stock_divided_by_daily_consumption() -> None:
    assert calculate_coverage_days(3000, 1000) == 3


def test_monitoring_classifies_five_day_delay_against_three_day_buffer_as_high() -> None:
    result = MonitoringAgent().analyze(
        DisruptionEvent(title="Ship delayed", description="A vessel is delayed.", delay_days=5),
        coverage_days=3,
    )

    assert result.severity == Severity.HIGH
    assert result.significant is True
    assert result.reasoning


def test_procurement_economic_comparison_selects_vendor_b() -> None:
    inventory = MockSAPS4HANAClient().get_inventory("microchip-x")
    event = DisruptionEvent(title="Ship delayed", description="A vessel is delayed.", delay_days=5)
    logistics = LogisticsResult(
        agent="logistics",
        summary="Five day delay, three day coverage.",
        reasoning="Three days of stock cover a five-day delay.",
        inventory=inventory,
        coverage_days=3,
        stockout_days=2,
        cost_of_inaction=200000,
    )
    result = ProcurementAgent(MockAribaClient(), Settings()).compare(event, inventory, logistics)
    feasible = [item for item in result.evaluations if item.feasible]
    selected = min(feasible, key=lambda item: (item.risk_adjusted_total, item.vendor.risk_score))

    assert len(result.evaluations) == 4
    assert selected.vendor.vendor_id == "vendor-b"
    assert selected.risk_adjusted_total < logistics.cost_of_inaction
    assert result.reasoning
