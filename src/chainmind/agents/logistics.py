"""Logistics agent for stock coverage and production-loss estimates."""

from chainmind.core.models import DisruptionEvent, InventorySnapshot, LogisticsResult


def calculate_coverage_days(current_stock: int, daily_consumption: int) -> float:
    """Calculate how many production days the current inventory can cover."""

    if current_stock < 0:
        raise ValueError("Current stock cannot be negative.")
    if daily_consumption <= 0:
        raise ValueError("Daily consumption must be greater than zero.")
    return current_stock / daily_consumption


class LogisticsAgent:
    """Quantify a disruption's stockout exposure and inaction cost."""

    def analyze(self, event: DisruptionEvent, inventory: InventorySnapshot) -> LogisticsResult:
        """Calculate coverage, stockout duration, and estimated line-stoppage loss."""

        coverage_days = calculate_coverage_days(
            inventory.current_stock, inventory.daily_consumption
        )
        stockout_days = max(event.delay_days - coverage_days, 0.0)
        cost_of_inaction = stockout_days * inventory.line_stoppage_cost_per_day
        summary = (
            f"{inventory.current_stock:,} units cover {coverage_days:g} days; "
            f"estimated stockout is {stockout_days:g} days (${cost_of_inaction:,.0f})."
        )
        reasoning = (
            f"Coverage is current stock ({inventory.current_stock:,}) divided by daily "
            f"consumption ({inventory.daily_consumption:,}) = {coverage_days:g} days. "
            f"A {event.delay_days:g}-day delay leaves {stockout_days:g} stockout days, "
            f"with estimated inaction loss of ${cost_of_inaction:,.0f} at "
            f"${inventory.line_stoppage_cost_per_day:,.0f} per day."
        )
        return LogisticsResult(
            agent="logistics",
            summary=summary,
            reasoning=reasoning,
            inventory=inventory,
            coverage_days=coverage_days,
            stockout_days=stockout_days,
            cost_of_inaction=cost_of_inaction,
        )
