"""Local multi-process launcher configuration tests."""

from pathlib import Path

from scripts.run_all import service_definitions


def test_local_launcher_starts_all_services_with_mock_oidc_and_health_probes(
    tmp_path: Path,
) -> None:
    services = service_definitions(tmp_path, python="python")

    assert [service.name for service in services] == [
        "SAP/OIDC sandbox",
        "ChainMind API",
        "Dashboard",
    ]
    assert [service.health_url for service in services] == [
        "http://127.0.0.1:8100/health",
        "http://127.0.0.1:8000/health",
        "http://127.0.0.1:5173/",
    ]
    assert services[1].environment["CHAINMIND_MODE"] == "mock"
    assert services[1].environment["CHAINMIND_AUTH_DEV_BYPASS"] == "false"
    assert (
        services[0].environment["SAP_SANDBOX_EVENT_BRIDGE_SECRET"]
        == (services[1].environment["CHAINMIND_EVENT_BRIDGE_SECRET"])
    )
    assert services[2].environment["VITE_OIDC_ISSUER"] == "http://127.0.0.1:8100"
    assert services[2].cwd == tmp_path / "dashboard"


def test_demo_groups_internal_stages_into_the_proposal_six_stage_flow() -> None:
    from chainmind.core.models import StageResult
    from scripts.run_demo import format_demo_stages

    stages = [
        StageResult(name="Monitoring", status="COMPLETED", summary="Disruption detected."),
        StageResult(name="Logistics", status="COMPLETED", summary="Impact calculated."),
        StageResult(name="Procurement", status="COMPLETED", summary="Vendors compared."),
        StageResult(name="Orchestrator", status="COMPLETED", summary="Vendor selected."),
        StageResult(name="Human approval", status="PENDING", summary="Approval required."),
        StageResult(name="PO execution", status="WAITING_FOR_APPROVAL", summary="Not executed."),
        StageResult(
            name="Execution & tracking",
            status="WAITING_FOR_APPROVAL",
            summary="Tracking waits.",
        ),
    ]

    result = format_demo_stages(stages)

    assert [line.split("]")[0].removeprefix("[") for line in result] == [
        "Deteksi Gangguan",
        "Analisis Dampak",
        "Pencarian Solusi",
        "Analisis & Keputusan",
        "Human-in-the-Loop",
        "Eksekusi Purchase Order",
    ]
    assert "WAITING_FOR_APPROVAL, WAITING_FOR_APPROVAL" in result[-1]


def test_demo_can_render_the_six_stage_labels_in_english() -> None:
    from chainmind.core.models import StageResult
    from scripts.run_demo import format_demo_stages

    result = format_demo_stages(
        [StageResult(name="Monitoring", status="COMPLETED", summary="Detected.")],
        language="en",
    )

    assert result[0].startswith("[Disruption detection]")
    assert result[1].startswith("[Impact analysis]")
