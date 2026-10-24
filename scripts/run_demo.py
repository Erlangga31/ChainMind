"""Run and print the deterministic end-to-end disruption demonstration."""

import argparse
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
DEMO_STAGE_LABELS_EN = (
    "Disruption detection",
    "Impact analysis",
    "Solution search",
    "Analysis & decision",
    "Human-in-the-loop",
    "Purchase-order execution",
)


def format_demo_stages(stages: list[StageResult], language: str = "id") -> list[str]:
    """Group internal workflow stages under the six proposal demo labels."""

    lines = []
    labels = [label for label, _ in DEMO_STAGE_GROUPS] if language == "id" else DEMO_STAGE_LABELS_EN
    for (_, names), display_label in zip(DEMO_STAGE_GROUPS, labels, strict=True):
        matched = [stage for stage in stages if any(name in stage.name.lower() for name in names)]
        if matched:
            status = ", ".join(stage.status for stage in matched)
            summary = " ".join(stage.summary for stage in matched)
            lines.append(f"[{display_label}] {status}: {summary}")
        else:
            waiting = (
                "Menunggu tahap sebelumnya."
                if language == "id"
                else "Waiting for the previous stage."
            )
            lines.append(f"[{display_label}] WAITING: {waiting}")
    return lines


def main() -> None:
    """Run the seeded event and print the complete analysis and audit trail."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("id", "en"), default="id")
    language = parser.parse_args().language
    seed = files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    event = DisruptionEvent.model_validate_json(seed)
    event.language = language
    run = create_pipeline().run(event)
    heading = (
        f"Demo ChainMind - run {run.run_id}"
        if language == "id"
        else f"ChainMind demo - run {run.run_id}"
    )
    print(heading)
    print(
        f"Keparahan: {run.severity}; status: {run.status.value}"
        if language == "id"
        else f"Severity: {run.severity}; status: {run.status.value}"
    )
    for stage_line in format_demo_stages(run.stages, language):
        print(f"\n{stage_line}")
    print("\nPerbandingan vendor:" if language == "id" else "\nVendor comparison:")
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
    print("\nDraf Purchase Order:" if language == "id" else "\nDraft Purchase Order:")
    print(json.dumps(run.draft_po.model_dump(mode="json"), indent=2))
    print("\nLog audit:" if language == "id" else "\nAudit log:")
    for entry in run.audit_log:
        print(
            f"- {entry.timestamp.isoformat()} [{entry.agent}] "
            f"{entry.input_summary} -> {entry.output_summary}"
        )
    print(
        "\nTidak ada tindakan finansial yang dieksekusi. Persetujuan manusia tetap diperlukan."
        if language == "id"
        else "\nNo financial action was executed. Human approval is still required."
    )


if __name__ == "__main__":
    main()
