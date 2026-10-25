"""Unit tests for offline demo preflight validation."""

from pathlib import Path

from scripts.preflight import is_port_available, run_preflight, supported_python


def test_python_support_matches_project_floor_and_ceiling() -> None:
    assert not supported_python((3, 11))
    assert supported_python((3, 12))
    assert supported_python((3, 13))
    assert not supported_python((3, 14))


def test_port_check_uses_bind_without_network_activity() -> None:
    assert isinstance(is_port_available(0), bool)


def test_preflight_reports_demo_resources_and_port_conflicts(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    for relative in (
        "dashboard/node_modules",
        "src/chainmind/data/sample_disruption.json",
        "src/chainmind/data/seed_inventory.json",
        "src/chainmind/data/seed_vendors.json",
        "sandbox/sap_sandbox/oidc.py",
    ):
        target = tmp_path / relative
        if relative.endswith("node_modules"):
            target.mkdir(parents=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((source / relative).read_text(encoding="utf-8"), encoding="utf-8")

    checks = run_preflight(tmp_path, port_checker=lambda port: port != 8000)
    results = {check.name: check for check in checks}

    assert results["Seed data"].passed
    assert results["OIDC demo users"].passed
    assert results["Port 8000"].passed is False
    assert results["Port 8100"].passed is True
