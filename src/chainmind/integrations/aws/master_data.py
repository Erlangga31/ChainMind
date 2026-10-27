"""DynamoDB-backed tenant master data for AWS-mode API requests."""

from __future__ import annotations

import csv
import io
import json
from random import Random
from typing import Literal
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from chainmind.core.errors import IntegrationError
from chainmind.core.master_data import (
    _ENTITY_KEYS,
    _ENTITY_MODELS,
    EntityModel,
    EntityName,
    GeneratedDataset,
    ImportReport,
    ImportRowError,
    MaterialRecord,
    SQLiteMasterDataStore,
    VendorOffer,
)


class DynamoDBMasterDataStore:
    """Persist tenant catalog records in the shared DynamoDB event table."""

    def __init__(self, table_name: str, region_name: str) -> None:
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    @staticmethod
    def _record_key(tenant_id: str, entity: str, record_id: str) -> str:
        return f"MASTER#{tenant_id}#{entity}#{record_id}"

    def _scan(self, expression: object) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        try:
            response = self._table.scan(FilterExpression=expression)
            items.extend(response.get("Items", []))
            while "LastEvaluatedKey" in response:
                response = self._table.scan(
                    FilterExpression=expression,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Tenant master data could not be read from DynamoDB.") from exc
        return items

    def list(self, entity: EntityName, tenant_id: str) -> list[EntityModel]:
        items = self._scan(
            Attr("record_type").eq("master_data")
            & Attr("tenant_id").eq(tenant_id)
            & Attr("entity").eq(entity)
        )
        model = _ENTITY_MODELS[entity]
        try:
            return [
                model.model_validate_json(str(item["record_json"]))
                for item in sorted(items, key=lambda value: str(value["record_id"]))
            ]
        except (KeyError, ValidationError) as exc:
            raise IntegrationError("A stored tenant master-data record is invalid.") from exc

    def get(self, entity: EntityName, tenant_id: str, record_id: str) -> EntityModel | None:
        try:
            response = self._table.get_item(
                Key={"run_id": self._record_key(tenant_id, entity, record_id)}
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Tenant master data could not be read from DynamoDB.") from exc
        item = response.get("Item")
        if not item:
            return None
        try:
            return _ENTITY_MODELS[entity].model_validate_json(str(item["record_json"]))
        except (KeyError, ValidationError) as exc:
            raise IntegrationError("A stored tenant master-data record is invalid.") from exc

    def put(self, entity: EntityName, tenant_id: str, record: EntityModel) -> EntityModel:
        record_id = str(getattr(record, _ENTITY_KEYS[entity]))
        try:
            self._table.put_item(
                Item={
                    "run_id": self._record_key(tenant_id, entity, record_id),
                    "record_type": "master_data",
                    "tenant_id": tenant_id,
                    "entity": entity,
                    "record_id": record_id,
                    "data_origin": record.data_origin,
                    "record_json": record.model_dump_json(),
                }
            )
            self._mark_initialized(tenant_id)
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Tenant master data could not be saved to DynamoDB.") from exc
        return record

    def delete(self, entity: EntityName, tenant_id: str, record_id: str) -> bool:
        existing = self.get(entity, tenant_id, record_id)
        if existing is None:
            return False
        try:
            self._table.delete_item(Key={"run_id": self._record_key(tenant_id, entity, record_id)})
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "Tenant master data could not be deleted from DynamoDB."
            ) from exc
        return True

    def replace(self, entity: EntityName, tenant_id: str, records: list[EntityModel]) -> None:
        for existing in self.list(entity, tenant_id):
            self.delete(entity, tenant_id, str(getattr(existing, _ENTITY_KEYS[entity])))
        for record in records:
            self.put(entity, tenant_id, record)

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
        model = _ENTITY_MODELS[entity]
        imported = 0
        errors: list[ImportRowError] = []
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
            except (ValueError, TypeError, ValidationError) as exc:
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

    def _is_initialized(self, tenant_id: str) -> bool:
        try:
            return bool(
                self._table.get_item(Key={"run_id": f"MASTER#{tenant_id}#bootstrap"}).get("Item")
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Tenant data bootstrap status could not be read.") from exc

    def _mark_initialized(self, tenant_id: str) -> None:
        self._table.put_item(
            Item={
                "run_id": f"MASTER#{tenant_id}#bootstrap",
                "record_type": "master_data_bootstrap",
                "tenant_id": tenant_id,
            }
        )

    def bootstrap_demo_data(self, tenant_id: str = "demo") -> bool:
        if self._is_initialized(tenant_id):
            return False
        seed_store = SQLiteMasterDataStore(":memory:")
        for entity in ("materials", "vendors", "shipments"):
            for record in seed_store.list(entity, "demo"):
                self.put(entity, tenant_id, record.model_copy(update={"data_origin": "demo"}))
        self._mark_initialized(tenant_id)
        return True

    def clear(self, tenant_id: str) -> None:
        for entity in ("materials", "vendors", "shipments", "events"):
            for record in self.list(entity, tenant_id):
                self.delete(entity, tenant_id, str(getattr(record, _ENTITY_KEYS[entity])))
        self._mark_initialized(tenant_id)

    def reset_demo_data(self, tenant_id: str) -> None:
        self.clear(tenant_id)
        try:
            self._table.delete_item(Key={"run_id": f"MASTER#{tenant_id}#bootstrap"})
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Tenant demo data could not be reset.") from exc
        self.bootstrap_demo_data(tenant_id)

    def generate_dataset(self, tenant_id: str, seed: int, size: int) -> GeneratedDataset:
        generator = Random(seed)
        material_count = max(1, min(size, 20))
        vendor_count = max(2, min(size * 2, 40))
        materials = [
            MaterialRecord(
                component_id=f"sample-{seed}-material-{index + 1}",
                component_name=f"Sample component {index + 1}",
                plant=generator.choice(["West Java", "Central Java", "East Java"]),
                current_stock=generator.randint(800, 12_000),
                daily_consumption=generator.randint(150, 2_500),
                safety_stock=generator.randint(100, 900),
                line_stoppage_cost_per_day=round(generator.uniform(15_000, 120_000), 2),
                purchase_quantity=generator.randint(1_000, 10_000),
                data_origin="generated",
            )
            for index in range(material_count)
        ]
        vendors = [
            VendorOffer(
                vendor_id=f"sample-{seed}-vendor-{index + 1}",
                vendor_name=f"Sample supplier {index + 1}",
                component_ids=[materials[index % material_count].component_id],
                region=generator.choice(["West Java", "Central Java", "East Java"]),
                distance_km=round(generator.uniform(10, 1_500), 1),
                lead_time_days=round(generator.uniform(1, 14), 1),
                unit_price=round(generator.uniform(5, 250), 2),
                capacity=generator.randint(1_000, 25_000),
                risk_score=generator.randint(5, 95),
                terms=generator.choice(["EXW", "FOB", "CIF", "Air Freight"]),
                data_origin="generated",
            )
            for index in range(vendor_count)
        ]
        for record in [*materials, *vendors]:
            self.put(
                "materials" if isinstance(record, MaterialRecord) else "vendors", tenant_id, record
            )
        return GeneratedDataset(
            seed=seed,
            materials=len(materials),
            vendors=len(vendors),
            shipments=0,
            disruptions=0,
        )

    def record_audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        entity: str,
        record_id: str,
    ) -> None:
        try:
            self._table.put_item(
                Item={
                    "run_id": f"MASTER#{tenant_id}#audit#{uuid4()}",
                    "record_type": "master_data_audit",
                    "tenant_id": tenant_id,
                    "actor": actor,
                    "action": action,
                    "entity": entity,
                    "record_id": record_id,
                }
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError("Master data changes could not be audited.") from exc

    def list_audit(self, tenant_id: str) -> list[dict[str, object]]:
        return self._scan(
            Attr("record_type").eq("master_data_audit") & Attr("tenant_id").eq(tenant_id)
        )
