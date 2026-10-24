"""Deterministic post-approval tracking calculations."""

from datetime import date, timedelta

from chainmind.agents.tracking import TrackingAgent
from chainmind.core.models import (
    InventorySnapshot,
    PurchaseOrder,
    ShipmentTracking,
    Vendor,
    VendorConfirmation,
)


def tracking_inputs(
    *,
    lead_time_days: float = 2,
    arrival_days: int = 2,
    confirmed_quantity: int = 5000,
    confirmation_status: str = "CONFIRMED",
) -> tuple[PurchaseOrder, Vendor, InventorySnapshot, VendorConfirmation, ShipmentTracking]:
    order = PurchaseOrder(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        component_id="microchip-x",
        component_name="Microchip X",
        quantity=5000,
        unit_price=27,
        total_price=135000,
    )
    vendor = Vendor(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        lead_time_days=lead_time_days,
        total_cost=135000,
        risk_score=88,
        capacity=10000,
    )
    inventory = InventorySnapshot(
        component_id="microchip-x",
        component_name="Microchip X",
        current_stock=3000,
        daily_consumption=1000,
        line_stoppage_cost_per_day=75000,
        purchase_quantity=5000,
    )
    confirmation = VendorConfirmation(
        confirmation_status=confirmation_status,
        confirmed_quantity=confirmed_quantity,
    )
    shipment = ShipmentTracking(
        tracking_id="ASN-1",
        status="IN_TRANSIT",
        estimated_arrival=date(2025, 1, 3) + timedelta(days=arrival_days),
    )
    return order, vendor, inventory, confirmation, shipment


def test_tracking_projects_stock_and_marks_illustrative_savings() -> None:
    order, vendor, inventory, confirmation, shipment = tracking_inputs()

    tracking, kpis = TrackingAgent().analyze(
        sap_reference="SAP-PO-1",
        ariba_reference="ARIBA-PO-1",
        order=order,
        vendor=vendor,
        inventory=inventory,
        confirmation=confirmation,
        shipment=shipment,
        cost_of_inaction=150000,
        estimated_stockout_days=2,
        simulated=True,
        today=date(2025, 1, 3),
    )

    assert tracking.inventory_projection.projected_stock_at_arrival == 6000
    assert tracking.inventory_projection.projected_coverage_days == 6
    assert tracking.line_stoppage_avoided is True
    assert tracking.eta_deviation_days == 0
    assert tracking.alert is None
    assert kpis.simulated is True
    assert kpis.illustrative_savings == 15000
    assert kpis.estimated_stockout_days_avoided == 2


def test_late_or_partial_confirmation_flags_deviation_and_line_risk() -> None:
    order, vendor, inventory, confirmation, shipment = tracking_inputs(
        lead_time_days=2,
        arrival_days=5,
        confirmed_quantity=4000,
        confirmation_status="PARTIAL",
    )

    tracking, kpis = TrackingAgent().analyze(
        sap_reference="SAP-PO-2",
        ariba_reference="ARIBA-PO-2",
        order=order,
        vendor=vendor,
        inventory=inventory,
        confirmation=confirmation,
        shipment=shipment,
        cost_of_inaction=150000,
        estimated_stockout_days=2,
        simulated=True,
        today=date(2025, 1, 3),
    )

    assert tracking.eta_deviation_days == 3
    assert tracking.alert is not None
    assert tracking.line_stoppage_avoided is False
    assert kpis.estimated_stockout_days_avoided == 0
