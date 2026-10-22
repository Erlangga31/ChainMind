"""Explicit placeholders for SAP Integration Suite connectivity."""

from chainmind.core.errors import IntegrationError
from chainmind.core.models import DisruptionEvent, InventorySnapshot, PurchaseOrder, Vendor


class RealSAPClient:
    """Placeholder adapter; implement OAuth and OData via SAP Integration Suite."""

    def get_inventory(self, component_id: str) -> InventorySnapshot:
        """Read inventory through the future SAP Integration Suite connection."""

        raise IntegrationError(
            "Real SAP S/4HANA connectivity is not configured; implement the "
            "Integration Suite adapter.",
            details={"component_id": component_id},
        )

    def create_draft_purchase_order(self, order: PurchaseOrder) -> PurchaseOrder:
        """Create a draft PO through SAP after the real adapter is configured."""

        raise IntegrationError(
            "Real SAP draft creation is not configured.",
            details={"po_id": str(order.po_id)},
        )

    def execute_purchase_order(self, order: PurchaseOrder) -> str:
        """Execute an approved PO through SAP after the real adapter is configured."""

        raise IntegrationError(
            "Real SAP purchase-order execution is not configured.",
            details={"po_id": str(order.po_id)},
        )


class RealAribaClient:
    """Placeholder adapter; implement supplier discovery through SAP Integration Suite."""

    def list_alternative_vendors(self, event: DisruptionEvent) -> list[Vendor]:
        """Query alternative suppliers through the future Ariba integration."""

        raise IntegrationError(
            "Real SAP Ariba connectivity is not configured.",
            details={"event_id": str(event.event_id)},
        )
