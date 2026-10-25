"""Helpers for consistently recording agent activity."""

from chainmind.core.models import AgentResult, AuditEntry


def audit_for(
    result: AgentResult,
    input_summary: str,
    *,
    proposal_step: int | None = None,
) -> AuditEntry:
    """Create an audit entry from a typed agent result."""

    return AuditEntry(
        agent=result.agent,
        input_summary=input_summary,
        output_summary=result.summary,
        reasoning=result.reasoning,
        proposal_step=proposal_step,
    )
