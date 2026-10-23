"""Language model adapter contract."""

from typing import Protocol

from chainmind.core.models import LLMExplanation, VendorEvaluation


class LLMClient(Protocol):
    """Produces a human-readable rationale from deterministic decision inputs."""

    def explain_vendor_choice(
        self,
        *,
        selected: VendorEvaluation,
        alternatives: list[VendorEvaluation],
        cost_of_inaction: float,
        run_id: str | None = None,
    ) -> LLMExplanation:
        """Explain the deterministic supplier choice and return source-attributed trace."""
