"""Workflow decision-state protections."""

from importlib.resources import files

import pytest

from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.events import EventStore
from chainmind.core.models import DecisionRequest, DecisionType, DisruptionEvent
from chainmind.factory import create_pipeline
from chainmind.workflow.definition import WorkflowState, validate_transition


def test_decision_cannot_be_replayed_after_rejection() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    event_json = (
        files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    )
    run = pipeline.run(DisruptionEvent.model_validate_json(event_json))

    pipeline.decide(
        run.run_id,
        DecisionRequest(decision=DecisionType.REJECT, note="Rejected for review."),
    )
    with pytest.raises(ChainMindError) as error:
        pipeline.decide(
            run.run_id,
            DecisionRequest(decision=DecisionType.APPROVE),
        )

    assert error.value.code == "decision_not_allowed"
    assert error.value.status_code == 409


def test_mock_runner_uses_the_shared_workflow_state_definition() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    run = pipeline.run(
        DisruptionEvent(
            title="Weather delay",
            description="Severe weather delayed a cargo vessel.",
            delay_days=5,
        )
    )

    assert run.workflow_state is WorkflowState.HUMAN_APPROVAL
    pipeline.decide(
        run.run_id,
        DecisionRequest(decision=DecisionType.REVISE, vendor_id="vendor-a"),
    )
    revised = pipeline.get_run(run.run_id)
    assert revised.workflow_state is WorkflowState.HUMAN_APPROVAL
    assert revised.revision_count == 1

    pipeline.decide(revised.run_id, DecisionRequest(decision=DecisionType.APPROVE))
    completed = pipeline.get_run(run.run_id)
    assert completed.workflow_state is WorkflowState.COMPLETED


def test_mock_runner_enforces_configured_revision_limit() -> None:
    pipeline = create_pipeline(
        Settings(mode="mock", max_revisions=1),
        EventStore(),
    )
    run = pipeline.run(
        DisruptionEvent(
            title="Weather delay",
            description="Severe weather delayed a cargo vessel.",
            delay_days=5,
        )
    )
    pipeline.decide(
        run.run_id,
        DecisionRequest(decision=DecisionType.REVISE, vendor_id="vendor-a"),
    )

    with pytest.raises(ChainMindError) as error:
        pipeline.decide(
            run.run_id,
            DecisionRequest(decision=DecisionType.REVISE, vendor_id="vendor-c"),
        )

    assert error.value.code == "revision_limit_reached"


def test_shared_workflow_definition_rejects_illegal_transition() -> None:
    with pytest.raises(ValueError, match="invalid"):
        validate_transition(WorkflowState.HUMAN_APPROVAL, WorkflowState.LOGISTICS)
