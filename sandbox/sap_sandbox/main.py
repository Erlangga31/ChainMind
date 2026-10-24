"""FastAPI application simulating SAP OData, Ariba, Event Mesh, and Workflow."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sap_sandbox.config import SandboxSettings, get_sandbox_settings
from sap_sandbox.models import (
    EventMeshPublishRequest,
    MaterialStock,
    PurchaseOrderStatusPatch,
    WorkflowDecisionRequest,
    WorkflowDraftUpdate,
    WorkflowTaskRequest,
)
from sap_sandbox.oidc import add_oidc_routes
from starlette.responses import Response
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT, HTTP_502_BAD_GATEWAY

from chainmind.core.models import DisruptionEvent, InventoryProjection, PurchaseOrder, Vendor
from chainmind.integrations.external.signing import SIGNATURE_HEADER, sign_payload

ODATA_STOCK_PATH = "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock"
ODATA_PO_PATH = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder"
FILTER_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+eq\s+"
    r"(?:(?:'((?:[^']|'')*)')|([-+]?(?:\d+(?:\.\d*)?|\.\d+))|(true|false))\s*$",
    re.IGNORECASE,
)
SCENARIOS_PATH = Path(__file__).parent / "data" / "scenarios.json"


@dataclass
class WorkflowTask:
    """Mutable approval task held in the process-local workflow simulator."""

    task_id: str
    run_id: str
    po_id: str
    status: str = "PENDING"
    decision: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, str | None]:
        """Return a JSON-ready representation of the task."""

        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "po_id": self.po_id,
            "status": self.status,
            "decision": self.decision,
            "note": self.note,
        }


@dataclass
class SandboxState:
    """In-memory records backing the local SAP sandbox."""

    orders: dict[str, PurchaseOrder] = field(default_factory=dict)
    ariba_orders: dict[str, PurchaseOrder] = field(default_factory=dict)
    inventory_projections: dict[str, InventoryProjection] = field(default_factory=dict)
    workflow_tasks: dict[str, WorkflowTask] = field(default_factory=dict)
    workflow_by_run: dict[str, str] = field(default_factory=dict)
    published_events: list[DisruptionEvent] = field(default_factory=list)
    workflow_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def odata_error(code: str, message: str, status_code: int) -> JSONResponse:
    """Build an OData v2-shaped error response."""

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": {"lang": "en", "value": message}}},
    )


def apply_odata_query(
    entities: list[dict[str, Any]],
    filter_expression: str | None,
    select_expression: str | None,
    top: int | None,
) -> list[dict[str, Any]]:
    """Apply the supported OData ``$filter``, ``$select``, and ``$top`` options."""

    selected = entities
    if filter_expression:
        match = FILTER_PATTERN.fullmatch(filter_expression)
        if not match:
            raise ValueError("Only simple OData equality filters are supported.")
        property_name, string_value, number_value, boolean_value = match.groups()
        if property_name not in (entities[0] if entities else {}):
            raise ValueError(f"Unknown OData property '{property_name}'.")
        if string_value is not None:
            expected: Any = string_value.replace("''", "'")
        elif number_value is not None:
            expected = float(number_value) if "." in number_value else int(number_value)
        else:
            expected = boolean_value.lower() == "true"
        selected = [entity for entity in selected if entity[property_name] == expected]

    if top is not None:
        selected = selected[:top]
    if select_expression:
        properties = [item.strip() for item in select_expression.split(",") if item.strip()]
        available = set(entities[0]) if entities else set()
        unknown = set(properties) - available
        if unknown:
            raise ValueError(f"Unknown OData properties: {', '.join(sorted(unknown))}.")
        selected = [{name: entity[name] for name in properties} for entity in selected]
    return selected


def load_scenarios() -> list[dict[str, Any]]:
    """Load the deterministic local disruption scenarios."""

    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def load_vendors() -> list[Vendor]:
    """Load the same vendor fixtures used by the ChainMind mock adapter."""

    raw = files("chainmind.data").joinpath("seed_vendors.json").read_text(encoding="utf-8")
    return [Vendor.model_validate(item) for item in json.loads(raw)]


async def post_webhook(
    url: str,
    payload: dict[str, Any],
    secret: str | None = None,
    *,
    require_signature: bool = False,
    headers: dict[str, str] | None = None,
) -> None:
    """Deliver a simulator webhook and sign event messages when requested."""

    if require_signature and not secret:
        raise ValueError("SAP_SANDBOX_EVENT_BRIDGE_SECRET must be configured.")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if secret:
        request_headers[SIGNATURE_HEADER] = sign_payload(body, secret)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            url,
            content=body,
            headers=request_headers,
        )
        response.raise_for_status()


def create_app(settings: SandboxSettings | None = None) -> FastAPI:
    """Create the SAP sandbox application with isolated in-memory state."""

    sandbox_settings = settings or get_sandbox_settings()
    state = SandboxState()
    inventory_raw = (
        files("chainmind.data").joinpath("seed_inventory.json").read_text(encoding="utf-8")
    )
    inventory_seed = json.loads(inventory_raw)
    stock = MaterialStock(
        Material=inventory_seed["component_id"],
        MaterialName=inventory_seed["component_name"],
        UnrestrictedStock=inventory_seed["current_stock"],
        DailyConsumption=inventory_seed["daily_consumption"],
        LineStoppageCostPerDay=inventory_seed["line_stoppage_cost_per_day"],
        PurchaseQuantity=inventory_seed["purchase_quantity"],
        Currency=inventory_seed["currency"],
        PurchaseTerms=inventory_seed["purchase_terms"],
    )
    vendors = load_vendors()
    app = FastAPI(title="ChainMind Local SAP Sandbox", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[sandbox_settings.oidc_redirect_uri.rstrip("/")],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    add_oidc_routes(
        app,
        issuer=sandbox_settings.oidc_issuer,
        audience=sandbox_settings.oidc_audience,
        client_id=sandbox_settings.oidc_client_id,
        redirect_uri=sandbox_settings.oidc_redirect_uri,
    )
    app.state.sandbox = state
    app.state.csrf_token = secrets.token_urlsafe(24)
    app.state.access_tokens: dict[str, float] = {}

    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next: Any) -> Response:
        """Enforce demo bearer tokens and CSRF protection for SAP operations."""

        if request.url.path.startswith(("/sap/", "/ariba/")):
            authorization = request.headers.get("Authorization", "")
            scheme, _, token = authorization.partition(" ")
            expires_at = app.state.access_tokens.get(token, 0.0)
            if (
                scheme.lower() != "bearer"
                or not token
                or expires_at <= time.monotonic()
                or not secrets.compare_digest(
                    authorization,
                    f"Bearer {token}",
                )
            ):
                return JSONResponse(
                    status_code=401,
                    content={"error": "invalid_token"},
                )
        csrf_protected = request.url.path.startswith(
            (
                ODATA_PO_PATH,
                "/sap/opu/odata/sap/Z_CHAINMIND_TRACKING_SRV/InventoryProjection",
            )
        )
        method = request.method.upper()
        if csrf_protected and method in {"POST", "PATCH"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not secrets.compare_digest(supplied, app.state.csrf_token):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "csrf_token_required",
                            "message": {
                                "lang": "en",
                                "value": "A valid X-CSRF-Token header is required.",
                            },
                        }
                    },
                )
        response = await call_next(request)
        if (
            csrf_protected
            and method == "GET"
            and request.headers.get("X-CSRF-Token", "").lower() == "fetch"
        ):
            response.headers["X-CSRF-Token"] = app.state.csrf_token
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Use OData error envelopes for invalid OData requests."""

        return odata_error("400", str(exc), HTTP_400_BAD_REQUEST)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report sandbox health and identify simulated services."""

        return {"status": "ok", "service": "local-sap-sandbox"}

    @app.post("/oauth/token", response_model=None)
    async def oauth_token(request: Request) -> dict[str, Any] | JSONResponse:
        """Issue a short-lived demo token for OAuth2 client-credentials requests."""

        form = await request.body()
        form_values = {key: value[0] for key, value in parse_qs(form.decode("utf-8")).items()}
        grant_type = form_values.get("grant_type")
        if not form_values.get("client_id") or not form_values.get("client_secret"):
            return JSONResponse(
                status_code=HTTP_400_BAD_REQUEST,
                content={"error": "invalid_client"},
            )
        if grant_type != "client_credentials":
            return JSONResponse(
                status_code=HTTP_400_BAD_REQUEST,
                content={"error": "unsupported_grant_type"},
            )
        access_token = secrets.token_urlsafe(32)
        expires_in = 3600
        app.state.access_tokens[access_token] = time.monotonic() + expires_in
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
        }

    @app.get(ODATA_STOCK_PATH, response_model=None)
    def get_material_stocks(
        filter_expression: str | None = Query(default=None, alias="$filter"),
        select_expression: str | None = Query(default=None, alias="$select"),
        top: int | None = Query(default=None, ge=0, alias="$top"),
    ) -> dict[str, Any] | JSONResponse:
        """Return seeded S/4HANA stock information using an OData collection envelope."""

        entities = [stock.model_dump(mode="json")]
        try:
            result = apply_odata_query(entities, filter_expression, select_expression, top)
        except ValueError as exc:
            return odata_error("400", str(exc), HTTP_400_BAD_REQUEST)
        return {"d": {"results": result}}

    @app.get(f"{ODATA_STOCK_PATH}/{{material_id}}", response_model=None)
    @app.get(f"{ODATA_STOCK_PATH}('{{material_id}}')", response_model=None)
    def get_material_stock(material_id: str) -> dict[str, Any] | JSONResponse:
        """Return a single S/4HANA stock record by material identifier."""

        if material_id != stock.Material:
            return odata_error("404", f"Material '{material_id}' was not found.", 404)
        return {"d": stock.model_dump(mode="json")}

    @app.get(
        "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_BillOfMaterialItem",
        response_model=None,
    )
    def get_bom_items(
        filter_expression: str | None = Query(default=None, alias="$filter"),
        select_expression: str | None = Query(default=None, alias="$select"),
        top: int | None = Query(default=None, ge=0, alias="$top"),
    ) -> dict[str, Any] | JSONResponse:
        """Return a deterministic bill-of-material record for Microchip X."""

        entities = [
            {
                "Material": stock.Material,
                "BillOfMaterial": "BOM-MICROCHIP-X",
                "Component": "silicon-wafer",
                "ComponentQuantity": 1,
                "Unit": "EA",
            }
        ]
        try:
            return {
                "d": {
                    "results": apply_odata_query(
                        entities,
                        filter_expression,
                        select_expression,
                        top,
                    )
                }
            }
        except ValueError as exc:
            return odata_error("400", str(exc), HTTP_400_BAD_REQUEST)

    @app.get("/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_ProductionSchedule")
    def get_production_schedule() -> dict[str, Any]:
        """Return a demo production schedule with daily Microchip X demand."""

        return {
            "d": {
                "results": [
                    {
                        "Material": stock.Material,
                        "ProductionLine": "ASSEMBLY-01",
                        "ScheduledDate": (date.today() + timedelta(days=1)).isoformat(),
                        "PlannedQuantity": stock.DailyConsumption,
                    }
                ]
            }
        }

    @app.get("/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_ScheduledReceipt")
    def get_scheduled_receipts() -> dict[str, Any]:
        """Return a demo scheduled receipt for the material."""

        return {
            "d": {
                "results": [
                    {
                        "Material": stock.Material,
                        "PurchaseOrder": "4500000001",
                        "ShipmentId": "SHIP-MICROCHIP-X-001",
                        "ExpectedDate": (date.today() + timedelta(days=5)).isoformat(),
                        "Quantity": 1000,
                    }
                ]
            }
        }

    @app.get(ODATA_PO_PATH, response_model=None)
    def list_purchase_orders(
        filter_expression: str | None = Query(default=None, alias="$filter"),
        select_expression: str | None = Query(default=None, alias="$select"),
        top: int | None = Query(default=None, ge=0, alias="$top"),
    ) -> dict[str, Any] | JSONResponse:
        """List simulated S/4HANA orders with supported OData query options."""

        entities = [order.model_dump(mode="json") for order in state.orders.values()]
        try:
            return {
                "d": {
                    "results": apply_odata_query(
                        entities,
                        filter_expression,
                        select_expression,
                        top,
                    )
                }
            }
        except ValueError as exc:
            return odata_error("400", str(exc), HTTP_400_BAD_REQUEST)

    @app.post(ODATA_PO_PATH, status_code=201, response_model=None)
    def create_purchase_order(order: PurchaseOrder) -> dict[str, Any] | JSONResponse:
        """Store a draft PO in PENDING_APPROVAL state."""

        order_key = str(order.po_id)
        if order_key in state.orders:
            return odata_error("409", "Purchase order already exists.", HTTP_409_CONFLICT)
        draft = order.model_copy(deep=True)
        draft.status = "PENDING_APPROVAL"
        state.orders[order_key] = draft
        return {"d": draft.model_dump(mode="json")}

    @app.get(f"{ODATA_PO_PATH}/{{po_id}}", response_model=None)
    @app.get(f"{ODATA_PO_PATH}('{{po_id}}')", response_model=None)
    def get_purchase_order(po_id: str) -> dict[str, Any] | JSONResponse:
        """Return a saved purchase order by ID."""

        order = state.orders.get(po_id)
        if order is None:
            return odata_error("404", "Purchase order was not found.", 404)
        return {"d": order.model_dump(mode="json")}

    @app.patch(f"{ODATA_PO_PATH}/{{po_id}}", response_model=None)
    @app.patch(f"{ODATA_PO_PATH}('{{po_id}}')", response_model=None)
    def patch_purchase_order(
        po_id: str,
        update: PurchaseOrderStatusPatch,
    ) -> dict[str, Any] | JSONResponse:
        """Update the status of a simulated purchase order."""

        order = state.orders.get(po_id)
        if order is None:
            return odata_error("404", "Purchase order was not found.", 404)
        order.status = update.status
        if update.status == "EXECUTED":
            order.sap_reference = f"MOCK-PO-{order.po_id.hex[:8].upper()}"
        return {"d": order.model_dump(mode="json")}

    @app.post("/sap/opu/odata/sap/Z_CHAINMIND_TRACKING_SRV/InventoryProjection")
    def save_inventory_projection(projection: InventoryProjection) -> dict[str, Any]:
        """Store the non-authoritative projected stock snapshot."""

        state.inventory_projections[projection.component_id] = projection
        return {"d": projection.model_dump(mode="json")}

    @app.get(
        "/sap/opu/odata/sap/Z_CHAINMIND_TRACKING_SRV/InventoryProjection",
        response_model=None,
    )
    def list_inventory_projections() -> dict[str, Any]:
        """Provide the collection read used to fetch CSRF tokens before writes."""

        return {
            "d": {
                "results": [
                    item.model_dump(mode="json") for item in state.inventory_projections.values()
                ]
            }
        }

    @app.get(
        "/sap/opu/odata/sap/Z_CHAINMIND_TRACKING_SRV/InventoryProjection/{component_id}",
        response_model=None,
    )
    def get_inventory_projection(component_id: str) -> dict[str, Any] | JSONResponse:
        """Return a stored illustrative inventory projection."""

        projection = state.inventory_projections.get(component_id)
        if projection is None:
            return odata_error("404", "Inventory projection was not found.", 404)
        return {"d": projection.model_dump(mode="json")}

    @app.get("/ariba/sourcing/vendors", response_model=None)
    def list_ariba_vendors(
        filter_expression: str | None = Query(default=None, alias="$filter"),
        select_expression: str | None = Query(default=None, alias="$select"),
        top: int | None = Query(default=None, ge=0, alias="$top"),
    ) -> dict[str, Any] | JSONResponse:
        """List alternative vendors from the shared ChainMind seed data."""

        entities = [vendor.model_dump(mode="json") for vendor in vendors]
        try:
            return {
                "d": {
                    "results": apply_odata_query(
                        entities,
                        filter_expression,
                        select_expression,
                        top,
                    )
                }
            }
        except ValueError as exc:
            return odata_error("400", str(exc), HTTP_400_BAD_REQUEST)

    @app.get("/ariba/sourcing/vendors/{vendor_id}/offers", response_model=None)
    def get_vendor_offers(vendor_id: str) -> dict[str, Any] | JSONResponse:
        """Return a vendor's lead-time, cost, capacity, and risk offer."""

        vendor = next((item for item in vendors if item.vendor_id == vendor_id), None)
        if vendor is None:
            return odata_error("404", "Vendor was not found.", 404)
        return {
            "d": {
                "results": [
                    {
                        **vendor.model_dump(mode="json"),
                        "rating": max(1, round(5 - vendor.risk_score / 25, 1)),
                    }
                ]
            }
        }

    @app.post("/ariba/po", response_model=None)
    def submit_ariba_purchase_order(order: PurchaseOrder) -> dict[str, Any] | JSONResponse:
        """Register an approved purchase order in the simulated supplier network."""

        key = str(order.po_id)
        state.ariba_orders.setdefault(key, order.model_copy(deep=True))
        return {"ariba_reference": f"MOCK-ARIBA-{order.po_id.hex[:8].upper()}"}

    @app.get("/ariba/po/{po_id}/confirmation", response_model=None)
    def get_vendor_confirmation(po_id: str) -> dict[str, Any] | JSONResponse:
        """Return a supplier confirmation only for a registered purchase order."""

        order = state.ariba_orders.get(po_id)
        if order is None:
            return odata_error("404", "Ariba purchase order was not found.", 404)
        return {
            "purchase_order_id": po_id,
            "confirmation_status": "CONFIRMED",
            "confirmed_quantity": order.quantity,
            "note": "Simulated supplier confirmation.",
        }

    @app.get("/ariba/po/{po_id}/asn", response_model=None)
    def get_advance_ship_notice(po_id: str) -> dict[str, Any] | JSONResponse:
        """Return an ASN using the lead time of the submitted PO's chosen vendor."""

        order = state.ariba_orders.get(po_id)
        if order is None:
            return odata_error("404", "Ariba purchase order was not found.", 404)
        vendor = next((item for item in vendors if item.vendor_id == order.vendor_id), None)
        if vendor is None:
            return odata_error("404", "The PO's supplier was not found.", 404)

        return {
            "purchase_order_id": po_id,
            "asn_id": f"ASN-{po_id[:8].upper()}",
            "status": "IN_TRANSIT",
            "estimated_arrival": (date.today() + timedelta(days=vendor.lead_time_days)).isoformat(),
            "note": "Simulated advance ship notice.",
        }

    @app.post("/event-mesh/publish", status_code=202, response_model=None)
    async def publish_event_mesh_event(
        request: EventMeshPublishRequest,
    ) -> dict[str, Any] | JSONResponse:
        """Publish a logistics event to the configured ChainMind webhook."""

        webhook_url = sandbox_settings.event_webhook_url
        try:
            await post_webhook(
                webhook_url,
                request.event.model_dump(mode="json"),
                sandbox_settings.event_bridge_secret,
                require_signature=True,
            )
        except (httpx.HTTPError, ValueError):
            return JSONResponse(
                status_code=HTTP_502_BAD_GATEWAY,
                content={
                    "error": {
                        "code": "webhook_delivery_failed",
                        "message": "The configured event webhook could not be reached.",
                    }
                },
            )
        state.published_events.append(request.event)
        return {
            "status": "published",
            "event_id": str(request.event.event_id),
            "webhook_url": webhook_url,
        }

    @app.get("/event-mesh/events")
    def list_published_events() -> dict[str, Any]:
        """List events published by the local Event Mesh simulator."""

        return {"events": [event.model_dump(mode="json") for event in state.published_events]}

    @app.get("/scenarios")
    def list_scenarios() -> list[dict[str, Any]]:
        """List seeded disruption scenarios available to the demo."""

        return load_scenarios()

    @app.post("/scenarios/{scenario_id}/inject", status_code=202, response_model=None)
    async def inject_scenario(scenario_id: str) -> dict[str, Any] | JSONResponse:
        """Send a seeded disruption scenario through the Event Mesh simulator."""

        scenario = next(
            (item for item in load_scenarios() if item["scenario_id"] == scenario_id),
            None,
        )
        if scenario is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "scenario_not_found", "message": scenario_id}},
            )
        event_data = {key: value for key, value in scenario.items() if key != "scenario_id"}
        event = DisruptionEvent.model_validate(event_data)
        try:
            await post_webhook(
                sandbox_settings.event_webhook_url,
                event.model_dump(mode="json"),
                sandbox_settings.event_bridge_secret,
                require_signature=True,
            )
        except (httpx.HTTPError, ValueError):
            return JSONResponse(
                status_code=HTTP_502_BAD_GATEWAY,
                content={
                    "error": {
                        "code": "webhook_delivery_failed",
                        "message": "The configured event webhook could not be reached.",
                    }
                },
            )
        state.published_events.append(event)
        return {
            "status": "published",
            "scenario_id": scenario_id,
            "event_id": str(event.event_id),
        }

    @app.post("/workflow/tasks", status_code=201)
    async def create_workflow_task(request: WorkflowTaskRequest) -> dict[str, Any]:
        """Create one idempotent approval task per ChainMind run."""

        async with state.workflow_lock:
            existing_id = state.workflow_by_run.get(request.run_id)
            if existing_id is not None:
                return state.workflow_tasks[existing_id].as_dict()
            task = WorkflowTask(
                task_id=str(uuid4()),
                run_id=request.run_id,
                po_id=request.po_id,
            )
            state.workflow_tasks[task.task_id] = task
            state.workflow_by_run[request.run_id] = task.task_id
            return task.as_dict()

    @app.get("/workflow/tasks/{task_id}", response_model=None)
    def get_workflow_task(task_id: str) -> dict[str, Any] | JSONResponse:
        """Return an approval task or a structured not-found response."""

        task = state.workflow_tasks.get(task_id)
        if task is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "task_not_found", "message": task_id}},
            )
        return task.as_dict()

    @app.post("/workflow/tasks/{task_id}/sync", response_model=None)
    async def sync_workflow_decision(
        task_id: str,
        decision: WorkflowDecisionRequest,
    ) -> dict[str, Any] | JSONResponse:
        """Synchronize a ChainMind decision without calling the run callback."""

        async with state.workflow_lock:
            task = state.workflow_tasks.get(task_id)
            if task is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "task_not_found", "message": task_id}},
                )
            if task.decision is not None and task.decision != decision.decision:
                return JSONResponse(
                    status_code=HTTP_409_CONFLICT,
                    content={
                        "error": {
                            "code": "decision_conflict",
                            "message": "The workflow task already has a different decision.",
                        }
                    },
                )
            task.status = "APPROVED" if decision.decision == "approve" else "REJECTED"
            task.decision = decision.decision
            task.note = decision.note
            return task.as_dict()

    @app.patch("/workflow/tasks/{task_id}/draft", response_model=None)
    async def update_workflow_draft(
        task_id: str,
        update: WorkflowDraftUpdate,
    ) -> dict[str, Any] | JSONResponse:
        """Associate a revised purchase-order draft with the pending task."""

        async with state.workflow_lock:
            task = state.workflow_tasks.get(task_id)
            if task is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "task_not_found", "message": task_id}},
                )
            if task.decision is not None:
                return JSONResponse(
                    status_code=HTTP_409_CONFLICT,
                    content={
                        "error": {
                            "code": "decision_already_recorded",
                            "message": "The workflow task already has a decision.",
                        }
                    },
                )
            task.po_id = update.po_id
            return task.as_dict()

    @app.post("/workflow/tasks/{task_id}/decision", response_model=None)
    async def decide_workflow_task(
        task_id: str,
        decision: WorkflowDecisionRequest,
    ) -> dict[str, Any] | JSONResponse:
        """Record a decision and call the ChainMind decision endpoint once."""

        async with state.workflow_lock:
            task = state.workflow_tasks.get(task_id)
            if task is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "task_not_found", "message": task_id}},
                )
            if task.decision is not None:
                if task.decision != decision.decision:
                    return JSONResponse(
                        status_code=HTTP_409_CONFLICT,
                        content={
                            "error": {
                                "code": "decision_conflict",
                                "message": "The workflow task already has a different decision.",
                            }
                        },
                    )
                return task.as_dict()
            task.status = "APPROVED" if decision.decision == "approve" else "REJECTED"
            task.decision = decision.decision
            task.note = decision.note
            callback_url = (
                f"{sandbox_settings.workflow_callback_url.rstrip('/')}/runs/{task.run_id}/decision"
            )
            callback_payload = {
                "decision": decision.decision,
                "note": decision.note,
            }
        try:
            await post_webhook(
                callback_url,
                callback_payload,
            )
        except httpx.HTTPError:
            async with state.workflow_lock:
                task.status = "PENDING"
                task.decision = None
                task.note = ""
            return JSONResponse(
                status_code=HTTP_502_BAD_GATEWAY,
                content={
                    "error": {
                        "code": "workflow_callback_failed",
                        "message": "The configured workflow callback could not be reached.",
                    }
                },
            )
        return task.as_dict()

    return app


app = create_app()
