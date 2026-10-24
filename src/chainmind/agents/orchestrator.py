"""Orchestrator agent for economic selection and draft purchase orders."""

from chainmind.core.errors import ChainMindError
from chainmind.core.models import (
    InventorySnapshot,
    LogisticsResult,
    OrchestratorResult,
    ProcurementResult,
    PurchaseOrder,
    ReasoningTraceStep,
    VendorEvaluation,
)
from chainmind.integrations.llm.base import LLMClient


class OrchestratorAgent:
    """Choose the lowest-cost feasible option and prepare a PO for approval."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def choose(
        self,
        procurement: ProcurementResult,
        logistics: LogisticsResult,
        *,
        vendor_id: str | None = None,
        run_id: str | None = None,
    ) -> OrchestratorResult:
        """Select the best economic option, optionally honoring a revision request."""

        feasible = [item for item in procurement.evaluations if item.feasible]
        if vendor_id is not None:
            selected = next((item for item in feasible if item.vendor.vendor_id == vendor_id), None)
            if selected is None:
                raise ChainMindError(
                    "vendor_not_feasible",
                    "The requested vendor is unknown or not feasible for this disruption.",
                    status_code=422,
                    details={"vendor_id": vendor_id},
                )
        else:
            if not feasible:
                raise ChainMindError(
                    "no_feasible_vendor",
                    "No vendor can meet the required capacity and disruption window.",
                    status_code=409,
                )
            selected = min(
                feasible,
                key=lambda item: (item.risk_adjusted_total, item.vendor.risk_score),
            )
        explanation = self._llm.explain_vendor_choice(
            selected=selected,
            alternatives=feasible,
            cost_of_inaction=logistics.cost_of_inaction,
            run_id=run_id,
        )
        trace = [
            ReasoningTraceStep(
                source="SAP S/4HANA",
                text=(
                    "Cost of inaction was computed from stock coverage and production-loss "
                    "inputs by deterministic Python logic."
                ),
            ),
            ReasoningTraceStep(
                source="SAP Ariba",
                text=f"Python evaluated {len(feasible)} feasible supplier offers.",
            ),
            *explanation.trace,
        ]
        return OrchestratorResult(
            agent="orchestrator",
            summary=(
                f"Selected {selected.vendor.vendor_name} at "
                f"${selected.risk_adjusted_total:,.0f} risk-adjusted total."
            ),
            reasoning=explanation.text,
            selected_vendor=selected,
            cost_of_inaction=logistics.cost_of_inaction,
            trace=trace,
            fallback_used=explanation.fallback_used,
            fallback_reason=explanation.fallback_reason,
        )

    @staticmethod
    def draft_purchase_order(
        selected: VendorEvaluation, inventory: InventorySnapshot
    ) -> PurchaseOrder:
        """Create a non-executed purchase order for human approval."""

        quantity = inventory.purchase_quantity
        unit_price = selected.action_cost / quantity
        return PurchaseOrder(
            vendor_id=selected.vendor.vendor_id,
            vendor_name=selected.vendor.vendor_name,
            component_id=inventory.component_id,
            component_name=inventory.component_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=unit_price * quantity,
            currency=inventory.currency,
            terms=inventory.purchase_terms,
        )
