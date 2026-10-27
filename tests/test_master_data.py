import json

from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.master_data import (
    MaterialRecord,
    SQLiteMasterDataStore,
    VendorOffer,
)
from chainmind.core.models import DisruptionEvent
from chainmind.factory import create_pipeline


def material(component_id: str = "custom-board") -> MaterialRecord:
    return MaterialRecord(
        component_id=component_id,
        component_name="Custom board",
        plant="North Plant",
        unit="pcs",
        current_stock=840,
        daily_consumption=210,
        safety_stock=80,
        line_stoppage_cost_per_day=32_000,
        purchase_quantity=1_000,
        purchase_terms="FOB",
    )


def offer(vendor_id: str, *, lead: float, price: float, risk: int) -> VendorOffer:
    return VendorOffer(
        vendor_id=vendor_id,
        vendor_name=f"Supplier {vendor_id}",
        component_ids=["custom-board"],
        region="North",
        distance_km=50,
        lead_time_days=lead,
        unit_price=price,
        capacity=5_000,
        risk_score=risk,
        terms="FOB",
    )


def test_demo_seed_bootstraps_once_and_can_be_cleared(tmp_path) -> None:
    database = tmp_path / "master-data.sqlite3"
    first = SQLiteMasterDataStore(database)
    assert first.list("materials", "demo")[0].data_origin == "demo"
    assert len(first.list("vendors", "demo")) == 4
    first.clear("demo")

    restarted = SQLiteMasterDataStore(database)
    assert restarted.list("materials", "demo") == []
    assert restarted.list("vendors", "demo") == []


def test_master_data_is_scoped_by_tenant_and_supports_create_update_delete(tmp_path) -> None:
    store = SQLiteMasterDataStore(tmp_path / "catalog.sqlite3")
    store.put("materials", "tenant-one", material())
    assert store.get("materials", "tenant-two", "custom-board") is None

    updated = material().model_copy(update={"current_stock": 1_000})
    store.put("materials", "tenant-one", updated)
    assert store.get("materials", "tenant-one", "custom-board").current_stock == 1_000
    assert store.delete("materials", "tenant-one", "custom-board") is True
    assert store.delete("materials", "tenant-one", "custom-board") is False


def test_import_reports_invalid_rows_without_dropping_valid_records(tmp_path) -> None:
    store = SQLiteMasterDataStore(tmp_path / "catalog.sqlite3")
    report = store.import_records(
        "materials",
        "tenant-one",
        json.dumps(
            [
                material().model_dump(mode="json"),
                {"component_id": "invalid", "component_name": "Missing required numbers"},
            ]
        ),
        "json",
    )

    assert report.imported == 1
    assert [error.row for error in report.errors] == [2]
    assert store.get("materials", "tenant-one", "custom-board") is not None
    assert (
        json.loads(store.export_records("materials", "tenant-one", "json"))[0]["component_id"]
        == "custom-board"
    )


def test_sample_generation_is_deterministic_for_same_seed_and_size(tmp_path) -> None:
    store = SQLiteMasterDataStore(tmp_path / "catalog.sqlite3")
    left = store.generate_dataset("tenant-one", seed=41, size=3)
    first_materials = store.list("materials", "tenant-one")
    first_vendors = store.list("vendors", "tenant-one")
    right = store.generate_dataset("tenant-one", seed=41, size=3)

    assert left == right
    assert first_materials == store.list("materials", "tenant-one")
    assert first_vendors == store.list("vendors", "tenant-one")
    assert left.materials == 3
    assert left.vendors >= 2


def test_pipeline_uses_user_created_inventory_and_vendor_offers(tmp_path) -> None:
    database = tmp_path / "pipeline.sqlite3"
    catalog = SQLiteMasterDataStore(database)
    catalog.put("materials", "tenant-one", material())
    catalog.put("vendors", "tenant-one", offer("fast", lead=2, price=30, risk=60))
    catalog.put("vendors", "tenant-one", offer("cheap", lead=6, price=10, risk=30))
    pipeline = create_pipeline(
        Settings(mode="mock", event_database_path=str(database)),
        store=EventStore(),
    )

    result = pipeline.run(
        DisruptionEvent(
            tenant_id="tenant-one",
            title="Custom material delivery delay",
            description="Inbound supplier shipment is delayed.",
            component_id="custom-board",
            component_name="Custom board",
            delay_days=5,
            event_type="logistics_delay",
            source="data-studio",
        )
    )

    assert result.inventory_snapshot is not None
    assert result.inventory_snapshot.current_stock == 840
    assert result.material_impacts[0].coverage_days == 4
    assert {item.vendor.vendor_id for item in result.vendor_comparison} == {"fast", "cheap"}
    assert result.draft_po is not None
    assert result.draft_po.vendor_id == "fast"
    assert result.draft_po.unit_price == 30
