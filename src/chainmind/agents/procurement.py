"""Procurement agent for quote collection and economic comparison."""

from chainmind.core.config import Settings
from chainmind.core.models import (
    DisruptionEvent,
    InventorySnapshot,
    LogisticsResult,
    ProcurementResult,
    Vendor,
    VendorEvaluation,
)
from chainmind.integrations.sap.base import AribaClient


class ProcurementAgent:
    """Evaluate alternative vendors using capacity, timing, cost, and risk."""

    def __init__(self, ariba: AribaClient, settings: Settings) -> None:
        self._ariba = ariba
        self._settings = settings

    def compare(
        self,
        event: DisruptionEvent,
        inventory: InventorySnapshot,
        logistics: LogisticsResult,
    ) -> ProcurementResult:
        """Compare all supplier quotes and identify feasible mitigation options."""

        vendors = self._ariba.list_alternative_vendors(event)
        evaluations = [self._evaluate(vendor, inventory, logistics) for vendor in vendors]
        evaluations.sort(
            key=lambda item: (
                not item.feasible,
                not item.same_region,
                item.vendor.distance_km,
                item.risk_adjusted_total,
            )
        )
        summary = (
            f"Compared {len(evaluations)} vendors; "
            f"{sum(item.feasible for item in evaluations)} are feasible."
        )
        reasoning = (
            f"Compared {len(evaluations)} Ariba supplier quotes against the "
            f"{inventory.purchase_quantity:,}-unit requirement, delivery window, "
            "risk-adjusted stockout exposure, and total landed cost."
        )
        return ProcurementResult(
            agent="procurement",
            summary=summary,
            reasoning=reasoning,
            evaluations=evaluations,
        )

    def _evaluate(
        self,
        vendor: Vendor,
        inventory: InventorySnapshot,
        logistics: LogisticsResult,
    ) -> VendorEvaluation:
        action_cost = vendor.total_cost + vendor.expedite_cost + vendor.freight_cost
        effective_lead = vendor.lead_time_days + self._settings.safety_reserve_days
        residual_days = max(effective_lead - logistics.coverage_days, 0.0)
        residual_loss = (
            residual_days * inventory.line_stoppage_cost_per_day * vendor.risk_score / 100
        )
        original_stockout = logistics.stockout_days
        reduced_stockout = max(vendor.lead_time_days - logistics.coverage_days, 0.0)
        capacity_sufficient = vendor.capacity >= inventory.purchase_quantity
        meets_deadline = (
            vendor.lead_time_days
            <= logistics.coverage_days + self._settings.stockout_tolerance_days
        )
        feasible = capacity_sufficient and (meets_deadline or reduced_stockout < original_stockout)
        same_region = vendor.region.casefold() == inventory.plant_region.casefold()
        total = action_cost + residual_loss
        rationale = (
            f"{vendor.vendor_name}: ${action_cost:,.0f} landed action cost plus "
            f"${residual_loss:,.0f} risk-adjusted residual loss "
            f"({residual_days:g} reserve-adjusted stockout days); "
            f"{vendor.distance_km:g} km from the plant in {vendor.region}; "
            f"{'same-region' if same_region else 'cross-region'} sourcing; "
            f"{'capacity sufficient' if capacity_sufficient else 'capacity insufficient'}; "
            f"{'meets coverage deadline' if meets_deadline else 'misses coverage deadline'}; "
            f"{'feasible' if feasible else 'not feasible'}."
        )
        return VendorEvaluation(
            vendor=vendor,
            feasible=feasible,
            action_cost=action_cost,
            residual_stockout_days=residual_days,
            residual_stockout_loss=residual_loss,
            risk_adjusted_total=total,
            rationale=rationale,
            same_region=same_region,
            capacity_sufficient=capacity_sufficient,
            meets_deadline=meets_deadline,
        )
