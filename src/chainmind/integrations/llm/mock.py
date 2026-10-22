"""Offline deterministic LLM implementation."""

from chainmind.core.models import VendorEvaluation


class MockLLMClient:
    """Generate a stable explanation without network or AWS credentials."""

    def explain_vendor_choice(
        self,
        *,
        selected: VendorEvaluation,
        alternatives: list[VendorEvaluation],
        cost_of_inaction: float,
    ) -> str:
        """Return a rule-based explanation of the selected alternative."""

        ranked = sorted(alternatives, key=lambda item: item.risk_adjusted_total)
        other_options = [
            item for item in ranked if item.vendor.vendor_id != selected.vendor.vendor_id
        ]
        best_other = other_options[0] if other_options else None
        comparison = (
            f" The best other feasible option is {best_other.vendor.vendor_name} "
            f"at ${best_other.risk_adjusted_total:,.0f} risk-adjusted."
            if best_other
            else ""
        )
        if ranked[0].vendor.vendor_id != selected.vendor.vendor_id:
            return (
                f"{selected.vendor.vendor_name} was retained at a human's request. "
                f"Its {selected.vendor.lead_time_days:g}-day lead time has a "
                f"${selected.risk_adjusted_total:,.0f} risk-adjusted total compared "
                f"with ${ranked[0].risk_adjusted_total:,.0f} for the lowest-cost option "
                f"{ranked[0].vendor.vendor_name}; cost of inaction is "
                f"${cost_of_inaction:,.0f}.{comparison} The replacement draft still "
                "requires human approval before any SAP purchase-order execution."
            )
        return (
            f"{selected.vendor.vendor_name} is recommended: its "
            f"{selected.vendor.lead_time_days:g}-day "
            f"lead time has a ${selected.risk_adjusted_total:,.0f} risk-adjusted "
            f"response cost against ${cost_of_inaction:,.0f} cost of inaction. "
            f"Its risk-adjusted total is ${selected.risk_adjusted_total:,.0f}."
            f"{comparison} A human must approve the draft before any SAP purchase-order "
            "execution."
        )
