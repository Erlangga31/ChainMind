"""Run and print the deterministic end-to-end disruption demonstration."""

import json
from importlib.resources import files

from chainmind.core.models import DisruptionEvent, StageResult
from chainmind.factory import create_pipeline

DEMO_STAGE_GROUPS = (
    ("Deteksi Gangguan", ("monitoring",)),
    ("Analisis Dampak", ("logistics",)),
    ("Pencarian Solusi", ("procurement",)),
    ("Analisis & Keputusan", ("orchestrator",)),
    ("Human-in-the-Loop", ("human approval",)),
    ("Eksekusi Purchase Order", ("po execution", "execution & tracking")),
)


def format_demo_stages(stages: list[StageResult]) -> list[str]:
    """Group internal workflow stages under the six proposal demo labels."""

    lines = []
    for label, names in DEMO_STAGE_GROUPS:
        matched = [stage for stage in stages if any(name in stage.name.lower() for name in names)]
        if matched:
            status = ", ".join(stage.status for stage in matched)
            summary = " ".join(stage.summary for stage in matched)
            lines.append(f"[{label}] {status}: {summary}")
        else:
            lines.append(f"[{label}] WAITING: Menunggu tahap sebelumnya.")
    return lines


def main() -> None:
    """Run the seeded event and print the complete analysis and audit trail."""

    seed = files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    event = DisruptionEvent.model_validate_json(seed)
    run = create_pipeline().run(event)
    print(f"ChainMind demo - run {run.run_id}")
    print(f"Severity: {run.severity}; status: {run.status.value}")
    for stage_line in format_demo_stages(run.stages):
        print(f"\n{stage_line}")
    print("\nVendor comparison:")
    for evaluation in run.vendor_comparison:
        print(
            f"- {evaluation.vendor.vendor_name}: "
            f"feasible={evaluation.feasible}, "
            f"action=${evaluation.action_cost:,.0f}, "
            f"residual=${evaluation.residual_stockout_loss:,.0f}, "
            f"total=${evaluation.risk_adjusted_total:,.0f}"
        )
    print("\nChain of Thought:")
    for index, reasoning in enumerate(run.chain_of_thought, start=1):
        print(f"{index}. {reasoning}")
    print("\nDraft Purchase Order:")
    print(json.dumps(run.draft_po.model_dump(mode="json"), indent=2))
    print("\nAudit log:")
    for entry in run.audit_log:
        print(
            f"- {entry.timestamp.isoformat()} [{entry.agent}] "
            f"{entry.input_summary} -> {entry.output_summary}"
        )
    print("\nNo financial action was executed. Human approval is still required.")


if __name__ == "__main__":
    main()
