"""Typed models shared by ChainMind agents, adapters, and API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Base model with strict input validation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Severity(StrEnum):
    """Disruption severity levels."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RunStatus(StrEnum):
    """Lifecycle status for a disruption run."""

    ANALYZING = "ANALYZING"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class DecisionType(StrEnum):
    """Supported human decisions for a proposed purchase order."""

    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"


class DisruptionEvent(DomainModel):
    """External supply-chain disruption supplied by an operator or event source."""

    event_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=2_000)
    component_id: str = Field(default="microchip-x", min_length=1, max_length=100)
    component_name: str = Field(default="Microchip X", min_length=1, max_length=160)
    delay_days: float = Field(gt=0, le=365)
    source: str = Field(default="external-logistics", max_length=100)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InventorySnapshot(DomainModel):
    """SAP inventory and production economics for one component."""

    component_id: str
    component_name: str
    current_stock: int = Field(ge=0)
    daily_consumption: int = Field(gt=0)
    line_stoppage_cost_per_day: float = Field(gt=0)
    purchase_quantity: int = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    purchase_terms: str = Field(default="Air Freight")


class Vendor(DomainModel):
    """Alternative supplier quote returned by the SAP Ariba adapter."""

    vendor_id: str
    vendor_name: str
    lead_time_days: float = Field(gt=0)
    total_cost: float = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    risk_score: int = Field(ge=0, le=100)
    capacity: int = Field(gt=0)
    expedite_cost: float = Field(default=0, ge=0)
    freight_cost: float = Field(default=0, ge=0)


class VendorEvaluation(DomainModel):
    """Economic and operational comparison for one vendor."""

    vendor: Vendor
    feasible: bool
    action_cost: float
    residual_stockout_days: float
    residual_stockout_loss: float
    risk_adjusted_total: float
    rationale: str


class AgentResult(DomainModel):
    """Typed result produced by each agent stage."""

    agent: str
    summary: str
    reasoning: str


class MonitoringResult(AgentResult):
    """Monitoring agent classification and significance decision."""

    severity: Severity
    significant: bool
    coverage_days: float


class LogisticsResult(AgentResult):
    """Logistics agent inventory impact and cost estimate."""

    inventory: InventorySnapshot
    coverage_days: float
    stockout_days: float
    cost_of_inaction: float


class ProcurementResult(AgentResult):
    """Procurement agent's vendor comparison."""

    evaluations: list[VendorEvaluation]


class OrchestratorResult(AgentResult):
    """Orchestrator's selected vendor and generated decision rationale."""

    selected_vendor: VendorEvaluation
    cost_of_inaction: float


class AuditEntry(DomainModel):
    """Append-only record of an agent action or human decision."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str
    input_summary: str
    output_summary: str
    reasoning: str


class StageResult(DomainModel):
    """Dashboard-friendly status of one workflow stage."""

    name: str
    status: str
    summary: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PurchaseOrder(DomainModel):
    """Draft or human-approved SAP purchase order."""

    po_id: UUID = Field(default_factory=uuid4)
    sap_reference: str | None = None
    vendor_id: str
    vendor_name: str
    component_id: str
    component_name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)
    total_price: float = Field(gt=0)
    currency: str = "USD"
    terms: str = "Air Freight"
    status: str = "PENDING_APPROVAL"


class DisruptionRun(DomainModel):
    """Persisted result of one disruption analysis."""

    run_id: UUID = Field(default_factory=uuid4)
    event: DisruptionEvent
    status: RunStatus = RunStatus.ANALYZING
    severity: Severity | None = None
    significant: bool = False
    stages: list[StageResult] = Field(default_factory=list)
    vendor_comparison: list[VendorEvaluation] = Field(default_factory=list)
    selected_vendor_id: str | None = None
    chain_of_thought: list[str] = Field(default_factory=list)
    draft_po: PurchaseOrder | None = None
    audit_log: list[AuditEntry] = Field(default_factory=list)
    error: str | None = None
    revision_note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionRequest(DomainModel):
    """Human decision submitted through the API or dashboard."""

    decision: DecisionType
    note: str = Field(default="", max_length=1_000)
    vendor_id: str | None = Field(default=None, max_length=100)


class DecisionResult(DomainModel):
    """Result of recording a human decision."""

    run_id: UUID
    status: RunStatus
    message: str
    draft_po: PurchaseOrder | None = None


class RunCreatedResponse(DomainModel):
    """Small response returned after a disruption is accepted."""

    run_id: UUID
    status: RunStatus
    severity: Severity | None = None


class ErrorResponse(DomainModel):
    """Structured API error payload."""

    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
