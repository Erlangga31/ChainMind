"""In-memory SAP S/4HANA adapter backed by packaged JSON seed data."""

import json
from importlib.resources import files

from chainmind.core.errors import IntegrationError
from chainmind.core.master_data import SQLiteMasterDataStore
from chainmind.core.models import (
    AffectedSupplyChainRecords,
    DisruptionEvent,
    InventoryProjection,
    InventorySnapshot,
    PurchaseOrder,
)


class MockSAPS4HANAClient:
    """OData-like local adapter for inventory reads and purchase-order records."""

    def __init__(self, master_data_store: SQLiteMasterDataStore | None = None) -> None:
        self._master_data = master_data_store
        self._inventory: dict[str, InventorySnapshot] = {}
        self._orders: dict[str, PurchaseOrder] = {}
        self._supply_chain_records: dict[str, dict[str, list[str]]] = {}
        self._projections: dict[str, InventoryProjection] = {}
        if self._master_data is None:
            self._load_inventory()
        raw_records = (
            files("chainmind.data")
            .joinpath("seed_supply_chain_records.json")
            .read_text(encoding="utf-8")
        )
        self._supply_chain_records = json.loads(raw_records)

    def _load_inventory(self) -> None:
        raw = files("chainmind.data").joinpath("seed_inventory.json").read_text(encoding="utf-8")
        initial_data = json.loads(raw)
        initial_items = initial_data if isinstance(initial_data, list) else [initial_data]
        snapshots = [InventorySnapshot.model_validate(item) for item in initial_items]
        additional_raw = (
            files("chainmind.data")
            .joinpath("seed_additional_inventory.json")
            .read_text(encoding="utf-8")
        )
        snapshots.extend(
            InventorySnapshot.model_validate(item) for item in json.loads(additional_raw)
        )
        self._inventory.update({snapshot.component_id: snapshot for snapshot in snapshots})

    def get_inventory(self, component_id: str, tenant_id: str = "demo") -> InventorySnapshot:
        """Return an OData-like inventory record."""

        if self._master_data is not None:
            self._master_data.bootstrap_demo_data(tenant_id)
            material = self._master_data.get("materials", tenant_id, component_id)
            if material is None:
                raise IntegrationError(
                    f"SAP S/4HANA has no inventory for component '{component_id}'.",
                    details={"component_id": component_id},
                )
            return material.inventory_snapshot(tenant_id)
        try:
            return self._inventory[component_id].model_copy(deep=True)
        except KeyError as exc:
            raise IntegrationError(
                f"SAP S/4HANA has no seeded inventory for component '{component_id}'.",
                details={"component_id": component_id},
            ) from exc

    def find_affected_records(self, event: DisruptionEvent) -> AffectedSupplyChainRecords:
        """Match a disruption to seeded shipment and locally drafted order records."""

        seeded = self._supply_chain_records.get(event.component_id, {})
        tenant_shipments = (
            self._master_data.list("shipments", event.tenant_id)
            if self._master_data is not None
            else []
        )
        open_orders = [
            *seeded.get("open_purchase_order_ids", []),
            *[
                order.po_id.hex
                for order in self._orders.values()
                if order.component_id == event.component_id
                and order.status not in {"EXECUTED", "REJECTED"}
            ],
        ]
        return AffectedSupplyChainRecords(
            component_id=event.component_id,
            shipment_ids=sorted(
                {
                    *seeded.get("shipment_ids", []),
                    *[
                        shipment.shipment_id
                        for shipment in tenant_shipments
                        if shipment.component_id == event.component_id
                    ],
                }
            ),
            open_purchase_order_ids=sorted(set(open_orders)),
        )

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

    def record_inventory_projection(self, projection: InventoryProjection) -> None:
        """Save an illustrative future stock projection without changing current stock."""

        self._projections[projection.component_id] = projection.model_copy(deep=True)

    def get_inventory_projection(self, component_id: str) -> InventoryProjection | None:
        """Return a copy of the latest projected replenishment snapshot."""

        projection = self._projections.get(component_id)
        return projection.model_copy(deep=True) if projection else None
