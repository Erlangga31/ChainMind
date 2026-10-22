"""Validated payloads used by the local SAP sandbox."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from chainmind.core.models import DisruptionEvent, PurchaseOrder


class SandboxModel(BaseModel):
    """Base sandbox schema that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MaterialStock(SandboxModel):
    """Material stock and consumption fields exposed as OData properties."""

    Material: str
    MaterialName: str
    UnrestrictedStock: int = Field(ge=0)
    DailyConsumption: int = Field(gt=0)
    LineStoppageCostPerDay: float = Field(gt=0)
    PurchaseQuantity: int = Field(gt=0)
    Currency: str = "USD"
    PurchaseTerms: str = "Air Freight"


class PurchaseOrderRequest(PurchaseOrder):
    """A purchase order submitted to the simulated S/4HANA service."""


class PurchaseOrderStatusPatch(SandboxModel):
    """Permitted purchase-order status updates."""

    status: Literal["PENDING_APPROVAL", "APPROVED", "EXECUTED", "REJECTED"]


class EventMeshPublishRequest(SandboxModel):
    """An event for the configured Event Mesh simulator webhook."""

    event: DisruptionEvent


class WorkflowTaskRequest(SandboxModel):
    """Create or retrieve an approval task for a run and draft PO."""

    run_id: str = Field(min_length=1, max_length=100)
    po_id: str = Field(min_length=1, max_length=100)


class WorkflowDecisionRequest(SandboxModel):
    """Approve or reject a sandbox workflow task."""

    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1_000)
