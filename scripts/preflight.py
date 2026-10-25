"""Offline preflight checks for the local ChainMind demo."""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PYTHON_PACKAGES = ("fastapi", "pydantic", "pydantic_settings", "boto3", "uvicorn")
DEMO_PORTS = (8100, 8000, 5173)


@dataclass(frozen=True)
class PreflightCheck:
    """One pass/fail result without configuration values or credentials."""

    name: str
    passed: bool
    detail: str


def supported_python(version: tuple[int, int]) -> bool:
    """The project supports Python 3.12 and 3.13."""

    return (3, 12) <= version < (3, 14)


def is_port_available(port: int) -> bool:
    """Return whether the local demo can bind its configured loopback port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _node_version() -> tuple[int, int, int] | None:
    try:
        output = subprocess.run(
            ["node", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    parts = output.removeprefix("v").split(".")
    try:
        if len(parts) < 3:
            return None
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def run_preflight(
    root: Path = ROOT,
    *,
    port_checker: Callable[[int], bool] = is_port_available,
) -> list[PreflightCheck]:
    """Check runtime, local dependencies, demo data, users, and ports without network calls."""

    checks = [
        PreflightCheck(
            "Python",
            supported_python(sys.version_info[:2]),
            f"{sys.version_info.major}.{sys.version_info.minor} (requires >=3.12,<3.14)",
        )
    ]
    node = _node_version()
    checks.append(
        PreflightCheck(
            "Node.js",
            node is not None and node >= (20, 19, 0),
            ".".join(map(str, node)) if node else "Not found (requires Node.js >=20.19)",
        )
    )
    missing = [name for name in REQUIRED_PYTHON_PACKAGES if importlib.util.find_spec(name) is None]
    checks.append(
        PreflightCheck(
            "Python dependencies",
            not missing,
            "Installed" if not missing else f"Missing: {', '.join(missing)}",
        )
    )
    dashboard_ready = (root / "dashboard" / "node_modules").is_dir()
    checks.append(
        PreflightCheck(
            "Dashboard dependencies",
            dashboard_ready,
            "dashboard/node_modules is present" if dashboard_ready else "Run npm ci in dashboard/",
        )
    )
    seed_paths = (
        root / "src" / "chainmind" / "data" / "sample_disruption.json",
        root / "src" / "chainmind" / "data" / "seed_inventory.json",
        root / "src" / "chainmind" / "data" / "seed_vendors.json",
    )
    missing_seed = [str(path.relative_to(root)) for path in seed_paths if not path.is_file()]
    checks.append(
        PreflightCheck(
            "Seed data",
            not missing_seed,
            "Disruption, inventory, and vendor fixtures found"
            if not missing_seed
            else f"Missing: {', '.join(missing_seed)}",
        )
    )
    oidc_file = root / "sandbox" / "sap_sandbox" / "oidc.py"
    oidc_text = oidc_file.read_text(encoding="utf-8") if oidc_file.is_file() else ""
    demo_users_present = (
        '"viewer"' in oidc_text and '"approver"' in oidc_text and '"password": "demo"' in oidc_text
    )
    checks.append(
        PreflightCheck(
            "OIDC demo users",
            demo_users_present,
            "viewer / demo and approver / demo configured"
            if demo_users_present
            else "Demo user definitions missing",
        )
    )
    for port in DEMO_PORTS:
        available = port_checker(port)
        checks.append(
            PreflightCheck(
                f"Port {port}",
                available,
                "Available" if available else "In use; stop the conflicting local service",
            )
        )
    return checks


def main() -> int:
    checks = run_preflight()
    for check in checks:
        print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    failed = sum(not check.passed for check in checks)
    print(f"\nPreflight: {len(checks) - failed}/{len(checks)} checks passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
