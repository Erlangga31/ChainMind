"""Tenant-scoped persistent master data for the local SAP simulation."""

from __future__ import annotations

import csv
import io
import json
import random
import sqlite3
from importlib.resources import files
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import Field

from chainmind.core.models import (
    DisruptionEvent,
    DomainModel,
    InventorySnapshot,
    Vendor,
)


class MaterialRecord(DomainModel):
    """User-managed inventory and production data for one material."""

    component_id: str = Field(min_length=1, max_length=100)
    component_name: str = Field(min_length=1, max_length=160)
    plant: str = Field(min_length=1, max_length=160)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    current_stock: int = Field(ge=0)
    daily_consumption: int = Field(gt=0)
    safety_stock: int = Field(default=0, ge=0)
    line_stoppage_cost_per_day: float = Field(gt=0)
    purchase_quantity: int = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    purchase_terms: str = Field(default="Standard", min_length=1, max_length=100)
    bom_component_ids: list[str] = Field(default_factory=list)
    data_origin: Literal["demo", "user", "generated"] = "user"

    def inventory_snapshot(self, tenant_id: str = "demo") -> InventorySnapshot:
        """Translate master data into the inventory contract consumed by agents."""

        return InventorySnapshot(
            tenant_id=tenant_id,
            component_id=self.component_id,
            component_name=self.component_name,
            current_stock=self.current_stock,
            daily_consumption=self.daily_consumption,
            line_stoppage_cost_per_day=self.line_stoppage_cost_per_day,
            purchase_quantity=self.purchase_quantity,
            currency=self.currency,
            purchase_terms=self.purchase_terms,
            plant_region=self.plant,
        )


class VendorOffer(DomainModel):
    """User-managed vendor quote associated with one or more materials."""

    vendor_id: str = Field(min_length=1, max_length=100)
    vendor_name: str = Field(min_length=1, max_length=160)
    component_ids: list[str] = Field(min_length=1)
    region: str = Field(min_length=1, max_length=160)
    distance_km: float = Field(ge=0)
    lead_time_days: float = Field(gt=0)
    unit_price: float = Field(gt=0)
    capacity: int = Field(gt=0)
    risk_score: int = Field(ge=0, le=100)
    terms: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    expedite_cost: float = Field(default=0, ge=0)
    freight_cost: float = Field(default=0, ge=0)
    data_origin: Literal["demo", "user", "generated"] = "user"

    def as_vendor(self, quantity: int) -> Vendor:
        """Return the Ariba quote representation for a material purchase."""

        return Vendor(
            vendor_id=self.vendor_id,
            vendor_name=self.vendor_name,
            lead_time_days=self.lead_time_days,
            total_cost=self.unit_price * quantity,
            currency=self.currency,
            risk_score=self.risk_score,
            capacity=self.capacity,
            expedite_cost=self.expedite_cost,
            freight_cost=self.freight_cost,
            region=self.region,
            distance_km=self.distance_km,
            terms=self.terms,
        )


class ShipmentRecord(DomainModel):
    """Open inbound shipment or purchase-order record."""

    shipment_id: str = Field(min_length=1, max_length=100)
    component_id: str = Field(min_length=1, max_length=100)
    vendor_id: str | None = None
    quantity: int = Field(gt=0)
    expected_date: str = Field(min_length=1, max_length=40)
    status: str = Field(default="OPEN", min_length=1, max_length=40)
    purchase_order_id: str | None = None
    data_origin: Literal["demo", "user", "generated"] = "user"


class DisruptionRecord(DisruptionEvent):
    """User-entered event stored before it is sent to the analysis pipeline."""

    data_origin: Literal["demo", "user", "generated"] = "user"


class ImportRowError(DomainModel):
    """One indexed validation issue from a bulk import."""

    row: int = Field(ge=1)
    message: str


class ImportReport(DomainModel):
    """Result of validating and importing independent records."""

    entity: str
    imported: int = Field(ge=0)
    errors: list[ImportRowError] = Field(default_factory=list)


class GeneratedDataset(DomainModel):
    """Counts and seed for a reproducible sample data generation."""

    seed: int
    materials: int
    vendors: int
    shipments: int
    disruptions: int


EntityName = Literal["materials", "vendors", "shipments", "events"]
EntityModel = MaterialRecord | VendorOffer | ShipmentRecord | DisruptionRecord
_ENTITY_MODELS = {
    "materials": MaterialRecord,
    "vendors": VendorOffer,
    "shipments": ShipmentRecord,
    "events": DisruptionRecord,
}
_ENTITY_KEYS = {
    "materials": "component_id",
    "vendors": "vendor_id",
    "shipments": "shipment_id",
    "events": "event_id",
}


class SQLiteMasterDataStore:
    """SQLite persistence shared by the API and mock SAP adapters."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        if str(database_path) != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS master_data (
                    tenant_id TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    data_origin TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, entity, record_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS master_data_bootstrap (
                    tenant_id TEXT PRIMARY KEY,
                    initialized INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS master_data_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        self.bootstrap_demo_data()

    def list(self, entity: EntityName, tenant_id: str) -> list[EntityModel]:
        model = _ENTITY_MODELS[entity]
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT record_json FROM master_data
                WHERE tenant_id = ? AND entity = ?
                ORDER BY record_id
                """,
                (tenant_id, entity),
            ).fetchall()
        return [model.model_validate_json(row["record_json"]) for row in rows]

    def get(self, entity: EntityName, tenant_id: str, record_id: str) -> EntityModel | None:
        model = _ENTITY_MODELS[entity]
        with self._lock:
            row = self._connection.execute(
                """
                SELECT record_json FROM master_data
                WHERE tenant_id = ? AND entity = ? AND record_id = ?
                """,
                (tenant_id, entity, record_id),
            ).fetchone()
        return model.model_validate_json(row["record_json"]) if row else None

    def put(self, entity: EntityName, tenant_id: str, record: EntityModel) -> EntityModel:
        record_id = str(getattr(record, _ENTITY_KEYS[entity]))
        payload = record.model_dump_json()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO master_data_bootstrap (tenant_id) VALUES (?)",
                (tenant_id,),
            )
            self._connection.execute(
                """
                INSERT INTO master_data
                    (tenant_id, entity, record_id, data_origin, record_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, entity, record_id) DO UPDATE SET
                    data_origin = excluded.data_origin,
                    record_json = excluded.record_json
                """,
                (tenant_id, entity, record_id, record.data_origin, payload),
            )
        return record

    def delete(self, entity: EntityName, tenant_id: str, record_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                DELETE FROM master_data
                WHERE tenant_id = ? AND entity = ? AND record_id = ?
                """,
                (tenant_id, entity, record_id),
            )
        return cursor.rowcount > 0

    def record_audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        entity: str,
        record_id: str,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO master_data_audit
                    (tenant_id, actor, action, entity, record_id, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (tenant_id, actor, action, entity, record_id),
            )

    def list_audit(self, tenant_id: str) -> list[dict[str, object]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT actor, action, entity, record_id, created_at
                FROM master_data_audit WHERE tenant_id = ?
                ORDER BY audit_id DESC
                """,
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace(self, entity: EntityName, tenant_id: str, records: list[EntityModel]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM master_data WHERE tenant_id = ? AND entity = ?",
                (tenant_id, entity),
            )
            for record in records:
                record_id = str(getattr(record, _ENTITY_KEYS[entity]))
                self._connection.execute(
                    """
                    INSERT INTO master_data
                        (tenant_id, entity, record_id, data_origin, record_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        entity,
                        record_id,
                        record.data_origin,
                        record.model_dump_json(),
                    ),
                )

    def import_records(
        self,
        entity: EntityName,
        tenant_id: str,
        content: str,
        file_format: Literal["csv", "json"],
    ) -> ImportReport:
        try:
            rows = (
                json.loads(content)
                if file_format == "json"
                else list(csv.DictReader(io.StringIO(content)))
            )
        except (json.JSONDecodeError, csv.Error) as exc:
            return ImportReport(
                entity=entity,
                imported=0,
                errors=[ImportRowError(row=1, message=str(exc))],
            )
        if not isinstance(rows, list):
            return ImportReport(
                entity=entity,
                imported=0,
                errors=[ImportRowError(row=1, message="Expected a JSON array of records.")],
            )
        imported = 0
        errors: list[ImportRowError] = []
        model = _ENTITY_MODELS[entity]
        for index, row in enumerate(rows, start=1):
            try:
                if not isinstance(row, dict):
                    raise ValueError("Record must be a JSON object or CSV row.")
                row = dict(row)
                for field_name in ("bom_component_ids", "component_ids", "affected_component_ids"):
                    value = row.get(field_name)
                    if isinstance(value, str) and value.startswith("["):
                        row[field_name] = json.loads(value)
                record = model.model_validate(row)
                if entity == "events":
                    record = record.model_copy(update={"tenant_id": tenant_id})
                self.put(entity, tenant_id, record)
                imported += 1
            except (ValueError, TypeError) as exc:
                errors.append(ImportRowError(row=index, message=str(exc)))
        return ImportReport(entity=entity, imported=imported, errors=errors)

    def export_records(
        self,
        entity: EntityName,
        tenant_id: str,
        file_format: Literal["csv", "json"],
    ) -> str:
        records = [record.model_dump(mode="json") for record in self.list(entity, tenant_id)]
        if file_format == "json":
            return json.dumps(records, ensure_ascii=False, indent=2)
        if not records:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
                    for key, value in record.items()
                }
            )
        return output.getvalue()

    def bootstrap_demo_data(self, tenant_id: str = "demo") -> bool:
        with self._lock, self._connection:
            initialized = self._connection.execute(
                "SELECT 1 FROM master_data_bootstrap WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if initialized:
                return False
            material_data = json.loads(
                files("chainmind.data").joinpath("seed_inventory.json").read_text(encoding="utf-8")
            )
            material_rows = material_data if isinstance(material_data, list) else [material_data]
            additional_rows = json.loads(
                files("chainmind.data")
                .joinpath("seed_additional_inventory.json")
                .read_text(encoding="utf-8")
            )
            vendors = json.loads(
                files("chainmind.data").joinpath("seed_vendors.json").read_text(encoding="utf-8")
            )
            for raw in [*material_rows, *additional_rows]:
                record = MaterialRecord(
                    component_id=raw["component_id"],
                    component_name=raw["component_name"],
                    plant=raw.get("plant_region", "Unknown"),
                    unit="pcs",
                    current_stock=raw["current_stock"],
                    daily_consumption=raw["daily_consumption"],
                    safety_stock=raw.get("safety_stock", 0),
                    line_stoppage_cost_per_day=raw["line_stoppage_cost_per_day"],
                    purchase_quantity=raw["purchase_quantity"],
                    currency=raw.get("currency", "USD"),
                    purchase_terms=raw.get("purchase_terms", "Standard"),
                    bom_component_ids=raw.get("bom_component_ids", []),
                    data_origin="demo",
                )
                self._insert_locked("materials", tenant_id, record)
            for raw in vendors:
                record = VendorOffer(
                    vendor_id=raw["vendor_id"],
                    vendor_name=raw["vendor_name"],
                    component_ids=[
                        item["component_id"] for item in [*material_rows, *additional_rows]
                    ],
                    region=raw.get("region", "Unknown"),
                    distance_km=raw.get("distance_km", 0),
                    lead_time_days=raw["lead_time_days"],
                    unit_price=raw["total_cost"] / 5000,
                    capacity=raw["capacity"],
                    risk_score=raw["risk_score"],
                    terms="Air Freight" if raw["vendor_id"] == "vendor-b" else "Standard",
                    currency=raw.get("currency", "USD"),
                    expedite_cost=raw.get("expedite_cost", 0),
                    freight_cost=raw.get("freight_cost", 0),
                    data_origin="demo",
                )
                self._insert_locked("vendors", tenant_id, record)
            supply_chain = json.loads(
                files("chainmind.data")
                .joinpath("seed_supply_chain_records.json")
                .read_text(encoding="utf-8")
            )
            for component_id, values in supply_chain.items():
                for shipment_id in values.get("shipment_ids", []):
                    self._insert_locked(
                        "shipments",
                        tenant_id,
                        ShipmentRecord(
                            shipment_id=shipment_id,
                            component_id=component_id,
                            quantity=5000,
                            expected_date="2026-10-27",
                            status="IN_TRANSIT",
                            data_origin="demo",
                        ),
                    )
            self._connection.execute(
                "INSERT INTO master_data_bootstrap (tenant_id) VALUES (?)",
                (tenant_id,),
            )
        return True

    def clear(self, tenant_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM master_data WHERE tenant_id = ?", (tenant_id,))
            self._connection.execute(
                "INSERT OR IGNORE INTO master_data_bootstrap (tenant_id) VALUES (?)",
                (tenant_id,),
            )

    def reset_demo_data(self, tenant_id: str) -> None:
        self.clear(tenant_id)
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM master_data_bootstrap WHERE tenant_id = ?",
                (tenant_id,),
            )
        self.bootstrap_demo_data(tenant_id)

    def generate_dataset(self, tenant_id: str, seed: int, size: int) -> GeneratedDataset:
        rng = random.Random(seed)
        materials_count = max(1, min(size, 20))
        vendors_count = max(2, min(size * 2, 40))
        materials = [
            MaterialRecord(
                component_id=f"sample-{seed}-material-{index + 1}",
                component_name=f"Sample component {index + 1}",
                plant=rng.choice(["West Java", "Central Java", "East Java"]),
                current_stock=rng.randint(800, 12_000),
                daily_consumption=rng.randint(150, 2_500),
                safety_stock=rng.randint(100, 900),
                line_stoppage_cost_per_day=round(rng.uniform(15_000, 120_000), 2),
                purchase_quantity=rng.randint(1_000, 10_000),
                data_origin="generated",
            )
            for index in range(materials_count)
        ]
        vendors = [
            VendorOffer(
                vendor_id=f"sample-{seed}-vendor-{index + 1}",
                vendor_name=f"Sample supplier {index + 1}",
                component_ids=[materials[index % len(materials)].component_id],
                region=rng.choice(["West Java", "Central Java", "East Java"]),
                distance_km=round(rng.uniform(10, 1_500), 1),
                lead_time_days=round(rng.uniform(1, 14), 1),
                unit_price=round(rng.uniform(5, 250), 2),
                capacity=rng.randint(1_000, 25_000),
                risk_score=rng.randint(5, 95),
                terms=rng.choice(["EXW", "FOB", "CIF", "Air Freight"]),
                data_origin="generated",
            )
            for index in range(vendors_count)
        ]
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO master_data_bootstrap (tenant_id) VALUES (?)",
                (tenant_id,),
            )
            for material in materials:
                self._insert_locked("materials", tenant_id, material)
            for vendor in vendors:
                self._insert_locked("vendors", tenant_id, vendor)
        return GeneratedDataset(
            seed=seed,
            materials=len(materials),
            vendors=len(vendors),
            shipments=0,
            disruptions=0,
        )

    def _insert_locked(self, entity: EntityName, tenant_id: str, record: EntityModel) -> None:
        record_id = str(getattr(record, _ENTITY_KEYS[entity]))
        self._connection.execute(
            """
            INSERT INTO master_data
                (tenant_id, entity, record_id, data_origin, record_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, entity, record_id) DO UPDATE SET
                data_origin = excluded.data_origin,
                record_json = excluded.record_json
            """,
            (tenant_id, entity, record_id, record.data_origin, record.model_dump_json()),
        )
