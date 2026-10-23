"""FastAPI endpoints for disruptions, run history, and human decisions."""

import logging
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chainmind.core.config import get_settings
from chainmind.core.errors import ChainMindError
from chainmind.core.models import (
    DecisionRequest,
    DecisionResult,
    DisruptionEvent,
    DisruptionRun,
    ErrorResponse,
    RunCreatedResponse,
)
from chainmind.factory import create_pipeline
from chainmind.integrations.external.signing import parse_signed_event

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
    allow_headers=["Content-Type", "X-ChainMind-Signature", "Idempotency-Key"],
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
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures without exposing stack traces or internals."""

    logger.error(
        "Unexpected API error",
        exc_info=(type(exc), exc, exc.__traceback__),
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
    run = pipeline.run(event)
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
    return RunCreatedResponse(run_id=run.run_id, status=run.status, severity=run.severity)


@app.get("/runs", response_model=list[DisruptionRun])
def list_runs() -> list[DisruptionRun]:
    """List locally persisted disruption analyses."""

    return pipeline.store.list()


@app.get("/runs/{run_id}", response_model=DisruptionRun)
def get_run(run_id: UUID) -> DisruptionRun:
    """Return full analysis, comparison, reasoning, draft PO, and audit."""

    return pipeline.get_run(run_id)


@app.post("/runs/{run_id}/decision", response_model=DecisionResult)
def decide(run_id: UUID, decision: DecisionRequest) -> DecisionResult:
    """Record an approval, rejection, or requested vendor revision."""

    return pipeline.decide(run_id, decision)
