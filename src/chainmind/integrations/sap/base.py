"""Contracts for SAP system-of-record adapters."""

from typing import Protocol

from chainmind.core.models import (
    AffectedSupplyChainRecords,
    DisruptionEvent,
    InventoryProjection,
    InventorySnapshot,
    PurchaseOrder,
    ShipmentTracking,
    Vendor,
    VendorConfirmation,
)


class SAPClient(Protocol):
    """Operations against SAP S/4HANA procurement and inventory."""

    def get_inventory(self, component_id: str, tenant_id: str = "demo") -> InventorySnapshot:
        """Read the current inventory and production economics."""

    def find_affected_records(self, event: DisruptionEvent) -> AffectedSupplyChainRecords:
        """Find shipments and open purchase orders for a disrupted material."""

    def create_draft_purchase_order(self, order: PurchaseOrder) -> PurchaseOrder:
        """Create a non-executed draft purchase order."""

    def execute_purchase_order(self, order: PurchaseOrder) -> str:
        """Execute an order only after explicit human approval."""

    def record_inventory_projection(self, projection: InventoryProjection) -> None:
        """Store the projected replenishment snapshot for operational visibility."""


class AribaClient(Protocol):
    """Operations against SAP Ariba Network."""

    def list_alternative_vendors(self, event: DisruptionEvent) -> list[Vendor]:
        """Return supplier quotes relevant to the disrupted component."""

    def submit_purchase_order(self, order: PurchaseOrder) -> str:
        """Send an approved purchase order to the selected supplier network."""

    def get_vendor_confirmation(self, order: PurchaseOrder) -> VendorConfirmation:
        """Retrieve the supplier's acknowledged order quantity and status."""

    def get_shipment_tracking(self, order: PurchaseOrder) -> ShipmentTracking:
        """Retrieve ASN and current estimated arrival details."""


class ApprovalWorkflowClient(Protocol):
    """Operations against an external approval workflow."""

    def create_task(self, run_id: str, po_id: str) -> str:
        """Create or retrieve an idempotent approval task."""

    def update_draft(self, task_id: str, po_id: str) -> None:
        """Associate a revised draft with the existing approval task."""

    def record_decision(self, task_id: str, decision: str, note: str) -> None:
        """Synchronize a decision made through the ChainMind dashboard."""
