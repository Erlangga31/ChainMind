"""HTTP clients for SAP S/4HANA and Ariba through Integration Suite."""

from __future__ import annotations

import json
from typing import Any, cast
from urllib.parse import quote

import boto3
import httpx
from botocore.exceptions import BotoCoreError
from pydantic import ValidationError

from chainmind.core.config import Settings
from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    AffectedSupplyChainRecords,
    DisruptionEvent,
    InventorySnapshot,
    PurchaseOrder,
    Vendor,
)
from chainmind.integrations.sap.http import SAPCredentials, SAPHttpTransport

MATERIAL_STOCK_PATH = "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock"
PURCHASE_ORDER_PATH = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder"
SCHEDULED_RECEIPT_PATH = "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_ScheduledReceipt"
ARIBA_VENDOR_PATH = "/ariba/sourcing/vendors"


def load_sap_credentials(settings: Settings) -> tuple[str, SAPCredentials, str]:
    """Resolve Integration Suite URL and OAuth credentials from settings or Secrets Manager."""

    base_url = settings.sap_integration_suite_url or settings.sap_base_url
    client_id = settings.sap_client_id
    client_secret = settings.sap_client_secret
    token_url = settings.sap_token_url
    if settings.mode == "aws":
        if not settings.sap_secrets_secret_id:
            raise IntegrationError("SAP Secrets Manager secret ID is required in AWS mode.")
        try:
            response = boto3.client(
                "secretsmanager",
                region_name=settings.aws_region,
            ).get_secret_value(SecretId=settings.sap_secrets_secret_id)
            secret_text = response.get("SecretString")
            if not isinstance(secret_text, str):
                raise ValueError("SecretString is missing.")
            secret = json.loads(secret_text)
            client_id = secret.get("client_id")
            client_secret = secret.get("client_secret")
            base_url = secret.get("integration_suite_url", base_url)
            token_url = secret.get("token_url", token_url)
        except (BotoCoreError, ValueError, TypeError) as exc:
            raise IntegrationError(
                "SAP credentials could not be loaded from Secrets Manager."
            ) from exc
    if not base_url or not token_url or not client_id or not client_secret:
        missing = [
            name
            for name, value in (
                ("CHAINMIND_SAP_INTEGRATION_SUITE_URL", base_url),
                ("CHAINMIND_SAP_TOKEN_URL", token_url),
                ("CHAINMIND_SAP_CLIENT_ID", client_id),
                ("CHAINMIND_SAP_CLIENT_SECRET", client_secret),
            )
            if not value
        ]
        raise IntegrationError(
            "SAP connection configuration is incomplete.",
            details={"missing_settings": missing},
        )
    return (
        cast(str, base_url),
        SAPCredentials(cast(str, client_id), cast(str, client_secret)),
        cast(str, token_url),
    )


def make_transport(settings: Settings) -> SAPHttpTransport:
    """Build a shared SAP transport from configured or AWS-managed credentials."""

    base_url, credentials, token_url = load_sap_credentials(settings)
    return SAPHttpTransport(
        base_url=base_url,
        token_url=token_url,
        credentials=credentials,
        timeout_seconds=settings.sap_timeout_seconds,
        retry_attempts=settings.retry_attempts,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
    )


def _odata_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("d", payload)
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        values = body["results"]
    elif isinstance(body, dict):
        values = [body]
    else:
        raise IntegrationError("SAP OData response has an invalid entity shape.")
    if not all(isinstance(item, dict) for item in values):
        raise IntegrationError("SAP OData response contains an invalid entity.")
    return values


def _map_error(exc: ValidationError, entity: str) -> IntegrationError:
    return IntegrationError(
        f"SAP returned an invalid {entity} record.",
        details={"validation_errors": exc.errors(include_input=False)},
    )


class RealS4HANAClient:
    """S/4HANA OData client authenticated through SAP Integration Suite."""

    def __init__(
        self,
        transport: SAPHttpTransport | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._transport = transport or make_transport(settings or Settings())

    def get_inventory(self, component_id: str) -> InventorySnapshot:
        """Fetch and validate a stock snapshot from the OData material entity."""

        payload = self._transport.request(
            "GET",
            MATERIAL_STOCK_PATH,
            params={"$filter": f"Material eq '{component_id.replace(chr(39), chr(39) * 2)}'"},
        )
        entities = _odata_results(payload)
        entity = next(
            (
                item
                for item in entities
                if item.get("Material") == component_id
                or item.get("MaterialNumber") == component_id
            ),
            None,
        )
        if entity is None:
            raise IntegrationError(
                "SAP S/4HANA has no inventory record for the requested component.",
                details={"component_id": component_id},
            )
        try:
            inventory = InventorySnapshot.model_validate(
                {
                    "component_id": entity.get(
                        "Material",
                        entity.get("MaterialNumber", entity.get("component_id")),
                    ),
                    "component_name": entity.get(
                        "MaterialName",
                        entity.get("MaterialDescription", entity.get("component_name")),
                    ),
                    "current_stock": entity.get("UnrestrictedStock", entity.get("CurrentStock")),
                    "daily_consumption": entity.get("DailyConsumption"),
                    "line_stoppage_cost_per_day": entity.get("LineStoppageCostPerDay"),
                    "purchase_quantity": entity.get("PurchaseQuantity"),
                    "currency": entity.get("Currency", "USD"),
                    "purchase_terms": entity.get("PurchaseTerms", "Air Freight"),
                },
            )
            if inventory.component_id != component_id:
                raise ValueError("SAP returned a different component ID.")
            return inventory
        except ValidationError as exc:
            raise _map_error(exc, "inventory") from exc
        except ValueError as exc:
            raise IntegrationError(
                "SAP returned an inventory record for the wrong component.",
                details={"component_id": component_id},
            ) from exc

    def find_affected_records(self, event: DisruptionEvent) -> AffectedSupplyChainRecords:
        """Match the disrupted material to scheduled receipts and open SAP orders."""

        escaped_id = event.component_id.replace("'", "''")
        receipt_payload = self._transport.request(
            "GET",
            SCHEDULED_RECEIPT_PATH,
            params={"$filter": f"Material eq '{escaped_id}'"},
        )
        receipts = _odata_results(receipt_payload)
        receipt_matches = [item for item in receipts if item.get("Material") == event.component_id]
        shipment_ids = [
            str(item["ShipmentId"]) for item in receipt_matches if item.get("ShipmentId")
        ]
        open_po_ids = {
            str(item.get("PurchaseOrder") or item.get("po_id"))
            for item in receipt_matches
            if item.get("PurchaseOrder") or item.get("po_id")
        }
        return AffectedSupplyChainRecords(
            component_id=event.component_id,
            shipment_ids=shipment_ids,
            open_purchase_order_ids=sorted(open_po_ids),
        )

    def create_draft_purchase_order(self, order: PurchaseOrder) -> PurchaseOrder:
        """Create an OData draft using a fetched CSRF token."""

        draft = order.model_copy(deep=True)
        draft.status = "PENDING_APPROVAL"
        response = self._transport.request(
            "POST",
            PURCHASE_ORDER_PATH,
            json_body=draft.model_dump(mode="json"),
            csrf=True,
        )
        entity = response.get("d", response)
        try:
            return PurchaseOrder.model_validate(entity)
        except ValidationError as exc:
            raise _map_error(exc, "purchase order") from exc

    def execute_purchase_order(self, order: PurchaseOrder) -> str:
        """Update an approved purchase order through an OData PATCH."""

        entity_path = f"{PURCHASE_ORDER_PATH}('{quote(str(order.po_id), safe='')}')"
        response = self._transport.request(
            "PATCH",
            entity_path,
            json_body={"status": "EXECUTED"},
            csrf=True,
        )
        entity = response.get("d", response)
        reference = entity.get("sap_reference") if isinstance(entity, dict) else None
        return str(reference or f"SAP-PO-{order.po_id}")


class RealAribaClient:
    """Ariba vendor sourcing client using the Integration Suite transport."""

    def __init__(
        self,
        transport: SAPHttpTransport | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._transport = transport or make_transport(settings or Settings())

    def list_alternative_vendors(self, event: DisruptionEvent) -> list[Vendor]:
        """Query and validate supplier offers for the disrupted component."""

        payload = self._transport.request("GET", ARIBA_VENDOR_PATH)
        try:
            return [Vendor.model_validate(item) for item in _odata_results(payload)]
        except ValidationError as exc:
            raise _map_error(exc, "vendor") from exc


class SandboxWorkflowClient:
    """HTTP client for approval tasks in the local SAP Business Workflow simulator."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    def create_task(self, run_id: str, po_id: str) -> str:
        """Create or retrieve an approval task for a draft purchase order."""

        try:
            response = self._client.post(
                f"{self._base_url}/workflow/tasks",
                json={"run_id": run_id, "po_id": po_id},
            )
            response.raise_for_status()
            task_id = response.json().get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("Workflow response omitted task_id.")
            return task_id
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationError("SAP Business Workflow task could not be created.") from exc

    def update_draft(self, task_id: str, po_id: str) -> None:
        """Replace the purchase-order reference on a pending workflow task."""

        try:
            response = self._client.patch(
                f"{self._base_url}/workflow/tasks/{quote(task_id, safe='')}/draft",
                json={"po_id": po_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IntegrationError("SAP Business Workflow draft could not be updated.") from exc

    def record_decision(self, task_id: str, decision: str, note: str) -> None:
        """Synchronize a decision submitted through ChainMind without another callback."""

        try:
            response = self._client.post(
                f"{self._base_url}/workflow/tasks/{quote(task_id, safe='')}/sync",
                json={"decision": decision, "note": note},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IntegrationError(
                "SAP Business Workflow decision could not be synchronized."
            ) from exc

    def close(self) -> None:
        """Close the workflow HTTP pool when owned by this client."""

        if self._owns_client:
            self._client.close()


class InMemoryApprovalWorkflowClient:
    """Local approval-task implementation for the fully offline mock preset."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, str]] = {}
        self._task_by_run: dict[str, str] = {}

    def create_task(self, run_id: str, po_id: str) -> str:
        """Create or retrieve a task using the run ID as an idempotency key."""

        task_id = self._task_by_run.get(run_id)
        if task_id is not None:
            return task_id
        task_id = f"mock-workflow-{run_id}"
        self._task_by_run[run_id] = task_id
        self._tasks[task_id] = {
            "po_id": po_id,
            "status": "PENDING",
            "decision": "",
            "note": "",
        }
        return task_id

    def record_decision(self, task_id: str, decision: str, note: str) -> None:
        """Record an idempotent offline approval decision."""

        task = self._tasks.get(task_id)
        if task is None:
            raise IntegrationError("Approval workflow task was not found.")
        if task["decision"] and task["decision"] != decision:
            raise IntegrationError("Approval workflow task already has a conflicting decision.")
        task.update(
            status="APPROVED" if decision == "approve" else "REJECTED",
            decision=decision,
            note=note,
        )

    def update_draft(self, task_id: str, po_id: str) -> None:
        """Replace the purchase-order reference on a pending in-memory task."""

        task = self._tasks.get(task_id)
        if task is None or task["decision"]:
            raise IntegrationError("Approval workflow task is unavailable for revision.")
        task["po_id"] = po_id

    def task_for_run(self, run_id: str) -> dict[str, str] | None:
        """Return a copy of the task for local diagnostics."""

        task_id = self._task_by_run.get(run_id)
        return self._tasks[task_id].copy() if task_id is not None else None
