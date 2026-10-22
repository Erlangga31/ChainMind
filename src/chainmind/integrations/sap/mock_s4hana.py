"""In-memory SAP S/4HANA adapter backed by packaged JSON seed data."""

from importlib.resources import files

from chainmind.core.errors import IntegrationError
from chainmind.core.models import InventorySnapshot, PurchaseOrder


class MockSAPS4HANAClient:
    """OData-like local adapter for inventory reads and purchase-order records."""

    def __init__(self) -> None:
        self._inventory: dict[str, InventorySnapshot] = {}
        self._orders: dict[str, PurchaseOrder] = {}
        self._load_inventory()

    def _load_inventory(self) -> None:
        raw = files("chainmind.data").joinpath("seed_inventory.json").read_text(encoding="utf-8")
        snapshot = InventorySnapshot.model_validate_json(raw)
        self._inventory[snapshot.component_id] = snapshot

    def get_inventory(self, component_id: str) -> InventorySnapshot:
        """Return an OData-like inventory record."""

        try:
            return self._inventory[component_id].model_copy(deep=True)
        except KeyError as exc:
            raise IntegrationError(
                f"SAP S/4HANA has no seeded inventory for component '{component_id}'.",
                details={"component_id": component_id},
            ) from exc

    def create_draft_purchase_order(self, order: PurchaseOrder) -> PurchaseOrder:
        """Store a draft PO without triggering downstream financial execution."""

        draft = order.model_copy(deep=True)
        draft.status = "PENDING_APPROVAL"
        self._orders[str(draft.po_id)] = draft
        return draft.model_copy(deep=True)

    def execute_purchase_order(self, order: PurchaseOrder) -> str:
        """Mark a previously drafted PO for execution after an approval decision."""

        stored = self._orders.get(str(order.po_id))
        if stored is None:
            raise IntegrationError(
                "SAP S/4HANA cannot execute a purchase order that was not drafted.",
                details={"po_id": str(order.po_id)},
            )
        stored.status = "EXECUTED"
        stored.sap_reference = f"MOCK-PO-{order.po_id.hex[:8].upper()}"
        return stored.sap_reference

    def get_order(self, po_id: str) -> PurchaseOrder | None:
        """Return a copy of a stored mock PO for local diagnostics."""

        order = self._orders.get(po_id)
        return order.model_copy(deep=True) if order else None
