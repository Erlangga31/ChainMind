"""Shared workflow states and allowed transitions for local and AWS runners."""

from enum import StrEnum


class WorkflowState(StrEnum):
    """Stable names shared by the mock pipeline and Step Functions definition."""

    INGESTED = "INGESTED"
    MONITORING = "MONITORING"
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
    LOGISTICS = "LOGISTICS"
    PROCUREMENT = "PROCUREMENT"
    ORCHESTRATOR = "ORCHESTRATOR"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    EXECUTION = "EXECUTION"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


WORKFLOW_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.INGESTED: frozenset({WorkflowState.MONITORING}),
    WorkflowState.MONITORING: frozenset({WorkflowState.NOT_SIGNIFICANT, WorkflowState.LOGISTICS}),
    WorkflowState.NOT_SIGNIFICANT: frozenset(),
    WorkflowState.LOGISTICS: frozenset({WorkflowState.PROCUREMENT}),
    WorkflowState.PROCUREMENT: frozenset({WorkflowState.ORCHESTRATOR}),
    WorkflowState.ORCHESTRATOR: frozenset({WorkflowState.HUMAN_APPROVAL}),
    WorkflowState.HUMAN_APPROVAL: frozenset(
        {WorkflowState.PROCUREMENT, WorkflowState.EXECUTION, WorkflowState.REJECTED}
    ),
    WorkflowState.EXECUTION: frozenset({WorkflowState.COMPLETED}),
    WorkflowState.COMPLETED: frozenset(),
    WorkflowState.REJECTED: frozenset(),
    WorkflowState.FAILED: frozenset(),
}


def validate_transition(current: WorkflowState, following: WorkflowState) -> None:
    """Raise for a transition absent from the shared workflow definition."""

    if following is WorkflowState.FAILED and current not in {
        WorkflowState.NOT_SIGNIFICANT,
        WorkflowState.COMPLETED,
        WorkflowState.REJECTED,
        WorkflowState.FAILED,
    }:
        return
    if following not in WORKFLOW_TRANSITIONS[current]:
        raise ValueError(f"Workflow transition {current.value} -> {following.value} is invalid.")
