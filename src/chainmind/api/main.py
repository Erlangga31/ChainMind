"""FastAPI endpoints for disruptions, run history, and human decisions."""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chainmind.core.config import get_settings
from chainmind.core.errors import ChainMindError
from chainmind.core.models import (
    AuditEntry,
    DecisionRequest,
    DecisionResult,
    DecisionType,
    DisruptionEvent,
    DisruptionRun,
    ErrorResponse,
    KPIReport,
    NotificationApprovalRequest,
    RunCreatedResponse,
    RunStatus,
)
from chainmind.factory import create_pipeline
from chainmind.integrations.aws.approval import StepFunctionsApprovalClient
from chainmind.integrations.aws.event_publisher import EventBridgePublisher
from chainmind.integrations.external.signing import parse_signed_event
from chainmind.workflow.definition import WorkflowState

logger = logging.getLogger("chainmind.api")
settings = get_settings()
pipeline = create_pipeline(settings)
app = FastAPI(
    title="ChainMind – Autonomous Disruption Resolver",
    version="0.1.0",
    description="Human-approved manufacturing supply-chain disruption response.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "X-ChainMind-Signature",
        "Idempotency-Key",
        "X-ChainMind-Role",
    ],
)


def _structured_log(
    event_name: str,
    *,
    run_id: UUID | None = None,
    **fields: str,
) -> None:
    """Emit a JSON record containing only explicitly safe operational fields."""

    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in {"mode", "status", "decision", "event_type", "exception_type"}
    }
    log_method = logger.error if event_name == "unexpected_api_error" else logger.info
    log_method(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event_name,
                "run_id": str(run_id) if run_id else None,
                **safe_fields,
            },
            separators=(",", ":"),
        )
    )


@app.exception_handler(ChainMindError)
async def chainmind_error_handler(_: Request, exc: ChainMindError) -> JSONResponse:
    """Translate expected domain and integration failures to structured JSON."""

    body = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a predictable error shape for invalid API requests."""

    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failure type without exposing request data or exception details."""

    _structured_log(
        "unexpected_api_error",
        run_id=UUID(request.path_params["run_id"]) if request.path_params.get("run_id") else None,
        mode=settings.mode,
        exception_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "The request could not be completed.",
            "details": {},
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Report local API health."""

    return {"status": "ok", "mode": settings.mode}


@app.post("/disruptions", response_model=RunCreatedResponse, status_code=201)
def ingest_disruption(
    event: DisruptionEvent,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunCreatedResponse:
    """Accept an event and run the disruption response pipeline."""

    if idempotency_key:
        event.idempotency_key = idempotency_key
    if settings.mode == "aws":
        try:
            canonical_event_id, _ = EventBridgePublisher(
                settings.event_table_name,
                settings.event_bus_name,
                settings.aws_region,
            ).publish(event)
        except ChainMindError as exc:
            raise ChainMindError(
                "event_publish_failed",
                "The disruption could not be published to the workflow.",
                status_code=503,
            ) from exc
        _structured_log(
            "disruption_published",
            run_id=canonical_event_id,
            mode=settings.mode,
            event_type=event.event_type.value if event.event_type else "unclassified",
        )
        return RunCreatedResponse(
            run_id=canonical_event_id,
            status=RunStatus.ANALYZING,
        )
    run = pipeline.run(event)
    _structured_log(
        "disruption_processed",
        run_id=run.run_id,
        mode=settings.mode,
        status=run.status.value,
        event_type=event.event_type.value if event.event_type else "unclassified",
    )
    return RunCreatedResponse(run_id=run.run_id, status=run.status, severity=run.severity)


@app.post("/event-bridge", response_model=RunCreatedResponse, status_code=202)
async def ingest_signed_event(request: Request) -> RunCreatedResponse:
    """Verify the Event Mesh HMAC signature before processing its event."""

    event = parse_signed_event(
        await request.body(),
        request.headers,
        settings.event_bridge_secret,
    )
    run = pipeline.run(event)
    _structured_log(
        "signed_event_processed",
        run_id=run.run_id,
        mode=settings.mode,
        status=run.status.value,
    )
    return RunCreatedResponse(run_id=run.run_id, status=run.status, severity=run.severity)


@app.get("/runs", response_model=list[DisruptionRun])
def list_runs() -> list[DisruptionRun]:
    """List locally persisted disruption analyses."""

    return pipeline.store.list()


@app.get("/kpis", response_model=KPIReport)
def get_kpis() -> KPIReport:
    """Return explicitly illustrative aggregate outcomes from completed tracking runs."""

    tracked = [run for run in pipeline.store.list() if run.kpis is not None]
    return KPIReport(
        simulated=any(run.kpis.simulated for run in tracked if run.kpis is not None),
        tracked_runs=len(tracked),
        executed_runs=sum(run.status == RunStatus.EXECUTED for run in tracked),
        line_stoppages_avoided=sum(
            bool(run.kpis and run.kpis.line_stoppage_avoided) for run in tracked
        ),
        illustrative_cost_of_inaction=sum(
            run.kpis.cost_of_inaction for run in tracked if run.kpis is not None
        ),
        illustrative_action_cost=sum(
            run.kpis.action_cost for run in tracked if run.kpis is not None
        ),
        illustrative_savings=sum(
            run.kpis.illustrative_savings for run in tracked if run.kpis is not None
        ),
    )


@app.get("/notifications/links/{token}")
def inspect_notification_link(token: str) -> dict[str, object]:
    """Inspect a signed link without taking an approval or financial action."""

    claims = pipeline.validate_notification_link(token)
    run = pipeline.get_run(claims.run_id)
    if claims.action == "approve":
        return {
            "run_id": str(run.run_id),
            "action": claims.action,
            "confirmation_required": True,
            "status": run.status,
            "vendor_name": run.draft_po.vendor_name if run.draft_po else None,
        }
    return {
        "run_id": str(run.run_id),
        "action": claims.action,
        "confirmation_required": False,
        "run": run.model_dump(mode="json"),
    }


@app.post("/notifications/links/{token}/approve", response_model=DecisionResult)
def approve_from_notification_link(
    token: str,
    confirmation: NotificationApprovalRequest,
    role: str | None = Header(default=None, alias="X-ChainMind-Role"),
) -> DecisionResult:
    """Require both an authenticated approver role and explicit link confirmation."""

    claims = pipeline.validate_notification_link(token)
    if claims.action != "approve":
        raise ChainMindError(
            "notification_action_mismatch",
            "This notification link is not an approval link.",
            status_code=403,
        )
    if role != "approver":
        raise ChainMindError(
            "approver_role_required",
            "Only a user with the approver role can decide a purchase order.",
            status_code=403,
        )
    if not confirmation.confirmed:
        raise ChainMindError(
            "approval_confirmation_required",
            "Explicit confirmation is required before submitting approval.",
            status_code=422,
        )
    return decide(
        claims.run_id,
        DecisionRequest(decision=DecisionType.APPROVE, note=confirmation.note),
        role,
    )


@app.get("/runs/{run_id}", response_model=DisruptionRun)
def get_run(run_id: UUID) -> DisruptionRun:
    """Return full analysis, comparison, reasoning, draft PO, and audit."""

    return pipeline.get_run(run_id)


@app.post("/runs/{run_id}/decision", response_model=DecisionResult)
def decide(
    run_id: UUID,
    decision: DecisionRequest,
    role: str | None = Header(default=None, alias="X-ChainMind-Role"),
) -> DecisionResult:
    """Record an approval, rejection, or requested vendor revision."""

    if role != "approver":
        raise ChainMindError(
            "approver_role_required",
            "Only a user with the approver role can decide a purchase order.",
            status_code=403,
        )
    if settings.mode == "aws":
        result = _decide_aws(run_id, decision, role)
    else:
        result = pipeline.decide(run_id, decision)
    _structured_log(
        "human_decision_recorded",
        run_id=run_id,
        mode=settings.mode,
        status=result.status.value,
        decision=decision.decision.value,
    )
    return result


def _decide_aws(run_id: UUID, decision: DecisionRequest, role: str) -> DecisionResult:
    """Resume a persisted Step Functions approval task in AWS mode."""

    run = pipeline.get_run(run_id)
    if run.last_decision == decision:
        return DecisionResult(
            run_id=run.run_id,
            status=run.status,
            message="This decision was already recorded.",
            draft_po=run.draft_po,
        )
    if run.status != RunStatus.PENDING_APPROVAL or run.draft_po is None:
        raise ChainMindError(
            "decision_not_allowed",
            "A decision can only be recorded for a draft pending approval.",
            status_code=409,
            details={"status": run.status.value},
        )
    if decision.decision is DecisionType.REVISE:
        if not decision.vendor_id:
            raise ChainMindError(
                "vendor_required",
                "A vendor_id is required when requesting a vendor revision.",
                status_code=422,
            )
        if run.revision_count >= settings.max_revisions:
            raise ChainMindError(
                "revision_limit_reached",
                "The maximum number of vendor revisions has been reached.",
                status_code=409,
                details={"max_revisions": settings.max_revisions},
            )
        if not any(
            item.vendor.vendor_id == decision.vendor_id and item.feasible
            for item in run.vendor_comparison
        ):
            raise ChainMindError(
                "vendor_not_feasible",
                "The selected vendor is not a feasible alternative for this run.",
                status_code=422,
                details={"vendor_id": decision.vendor_id},
            )
    StepFunctionsApprovalClient(
        settings.event_table_name,
        settings.aws_region,
    ).complete(run_id, decision, role)

    run.last_decision = decision.model_copy(deep=True)
    run.audit_log.append(
        AuditEntry(
            agent="human",
            input_summary=f"run_id={run.run_id}; role={role}",
            output_summary=f"Decision submitted: {decision.decision.value}.",
            reasoning=decision.note or "Authorized approver decision sent to Step Functions.",
        )
    )
    if decision.decision is DecisionType.REJECT:
        run.status = RunStatus.REJECTED
        run.workflow_state = WorkflowState.REJECTED
        run.draft_po.status = "REJECTED"
        for stage in run.stages:
            if stage.name == "Human approval":
                stage.status = "REJECTED"
            elif stage.name == "PO execution":
                stage.status = "NOT_EXECUTED"
            elif stage.name == "Execution & tracking":
                stage.status = "NOT_EXECUTED"
    elif decision.decision is DecisionType.APPROVE:
        run.status = RunStatus.APPROVED
        run.workflow_state = WorkflowState.EXECUTION
        run.draft_po.status = "APPROVED"
        for stage in run.stages:
            if stage.name == "Human approval":
                stage.status = "APPROVED"
            elif stage.name == "PO execution":
                stage.status = "IN_PROGRESS"
    else:
        run.revision_count += 1
        run.revision_note = decision.note
        run.workflow_state = WorkflowState.PROCUREMENT
    run.updated_at = datetime.now(UTC)
    pipeline.store.save(run)
    return DecisionResult(
        run_id=run.run_id,
        status=run.status,
        message=(
            "Decision sent to the Step Functions approval workflow."
            if decision.decision is not DecisionType.REJECT
            else "Draft rejected; no SAP purchase order will be executed."
        ),
        draft_po=run.draft_po,
    )
