"""Deterministic post-approval execution and inventory projection calculations."""

from datetime import date

from chainmind.core.models import (
    ExecutionTracking,
    InventoryProjection,
    InventorySnapshot,
    PurchaseOrder,
    RunKPI,
    ShipmentTracking,
    Vendor,
    VendorConfirmation,
)


class TrackingAgent:
    """Reconcile approved procurement with vendor confirmation and arrival data."""

    def analyze(
        self,
        *,
        sap_reference: str,
        ariba_reference: str,
        order: PurchaseOrder,
        vendor: Vendor,
        inventory: InventorySnapshot,
        confirmation: VendorConfirmation,
        shipment: ShipmentTracking,
        cost_of_inaction: float,
        estimated_stockout_days: float,
        simulated: bool,
        today: date | None = None,
    ) -> tuple[ExecutionTracking, RunKPI]:
        """Calculate arrival deviation, projected coverage, and illustrative economics."""

        as_of = today or date.today()
        arrival_days = max((shipment.estimated_arrival - as_of).days, 0)
        stock_at_arrival = max(
            inventory.current_stock - arrival_days * inventory.daily_consumption,
            0,
        )
        projected_stock = stock_at_arrival + confirmation.confirmed_quantity
        projected_coverage = projected_stock / inventory.daily_consumption
        eta_deviation = max(arrival_days - vendor.lead_time_days, 0)
        line_stoppage_avoided = (
            arrival_days <= inventory.current_stock / inventory.daily_consumption
            and confirmation.confirmation_status.upper() == "CONFIRMED"
            and confirmation.confirmed_quantity >= order.quantity
        )
        alert = (
            f"Vendor ETA is {eta_deviation:g} days later than the quoted lead time."
            if eta_deviation > 0
            else None
        )
        projection = InventoryProjection(
            component_id=inventory.component_id,
            current_stock=inventory.current_stock,
            daily_consumption=inventory.daily_consumption,
            confirmed_receipt_quantity=confirmation.confirmed_quantity,
            expected_arrival=shipment.estimated_arrival,
            projected_stock_at_arrival=projected_stock,
            projected_coverage_days=projected_coverage,
        )
        tracking = ExecutionTracking(
            sap_reference=sap_reference,
            ariba_reference=ariba_reference,
            confirmation=confirmation,
            shipment=shipment,
            inventory_projection=projection,
            line_stoppage_avoided=line_stoppage_avoided,
            eta_deviation_days=eta_deviation,
            alert=alert,
            simulated=simulated,
        )
        action_cost = order.total_price
        kpis = RunKPI(
            simulated=simulated,
            cost_of_inaction=cost_of_inaction,
            action_cost=action_cost,
            illustrative_savings=cost_of_inaction - action_cost,
            line_stoppage_avoided=line_stoppage_avoided,
            estimated_stockout_days_avoided=(
                estimated_stockout_days if line_stoppage_avoided else 0
            ),
        )
        return tracking, kpis
