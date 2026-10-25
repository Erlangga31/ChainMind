"""In-memory SAP Ariba vendor adapter backed by packaged seed data."""

import json
from datetime import date, timedelta
from importlib.resources import files

from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    DisruptionEvent,
    PurchaseOrder,
    ShipmentTracking,
    Vendor,
    VendorConfirmation,
)


class MockAribaClient:
    """Return deterministic alternative supplier quotes with OData-like data."""

    def __init__(self) -> None:
        raw = files("chainmind.data").joinpath("seed_vendors.json").read_text(encoding="utf-8")
        self._vendors = [Vendor.model_validate(item) for item in json.loads(raw)]
        self._submitted: dict[str, PurchaseOrder] = {}

    def list_alternative_vendors(self, event: DisruptionEvent) -> list[Vendor]:
        """Return seeded supplier offers for the requested component."""

        del event
        return [vendor.model_copy(deep=True) for vendor in self._vendors]

    def submit_purchase_order(self, order: PurchaseOrder) -> str:
        """Record a supplier submission after approval."""

        self._submitted[str(order.po_id)] = order.model_copy(deep=True)
        return f"MOCK-ARIBA-{order.po_id.hex[:8].upper()}"

    def get_vendor_confirmation(self, order: PurchaseOrder) -> VendorConfirmation:
        """Return a deterministic full-quantity supplier confirmation."""

        self._require_submitted(order)
        return VendorConfirmation(
            confirmation_status="CONFIRMED",
            confirmed_quantity=order.quantity,
            note="Simulated supplier confirmation.",
        )

    def get_shipment_tracking(self, order: PurchaseOrder) -> ShipmentTracking:
        """Return an illustrative shipment notice using the chosen vendor's lead time."""

        self._require_submitted(order)
        vendor = next(
            (item for item in self._vendors if item.vendor_id == order.vendor_id),
            None,
        )
        if vendor is None:
            raise IntegrationError(
                "The approved purchase order references an unknown Ariba vendor.",
                details={"vendor_id": order.vendor_id},
            )
        return ShipmentTracking(
            tracking_id=f"ASN-{order.po_id.hex[:8].upper()}",
            status="IN_TRANSIT",
            estimated_arrival=date.today() + timedelta(days=vendor.lead_time_days),
            note="Simulated advance ship notice.",
        )

    def _require_submitted(self, order: PurchaseOrder) -> None:
        if str(order.po_id) not in self._submitted:
            raise IntegrationError(
                "The Ariba supplier has not received this approved purchase order.",
                details={"po_id": str(order.po_id)},
            )
