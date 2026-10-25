"""Start the local SAP sandbox, ChainMind API, and Vite dashboard."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SECRET = "chainmind-local-demo-secret-change-before-deployment"


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    cwd: Path
    health_url: str
    environment: dict[str, str]


def service_definitions(root: Path = ROOT, python: str = sys.executable) -> tuple[Service, ...]:
    """Describe local processes and the health probes required before the demo."""

    dashboard_command = (
        ("cmd.exe", "/c", "npm.cmd", "run", "dev", "--", "--host", "127.0.0.1")
        if os.name == "nt"
        else ("npm", "run", "dev", "--", "--host", "127.0.0.1")
    )
    common_env = {
        "CHAINMIND_MODE": "mock",
        "CHAINMIND_AUTH_DEV_BYPASS": "false",
        "CHAINMIND_EVENT_BRIDGE_SECRET": LOCAL_SECRET,
        "CHAINMIND_NOTIFICATION_LINK_SECRET": "chainmind-signing-key-for-local-demo-only",
    }
    return (
        Service(
            name="SAP/OIDC sandbox",
            command=(
                python,
                "-m",
                "uvicorn",
                "sap_sandbox.main:app",
                "--app-dir",
                "sandbox",
                "--host",
                "127.0.0.1",
                "--port",
                "8100",
            ),
            cwd=root,
            health_url="http://127.0.0.1:8100/health",
            environment={
                "SAP_SANDBOX_EVENT_BRIDGE_SECRET": LOCAL_SECRET,
                "SAP_SANDBOX_EVENT_WEBHOOK_URL": "http://127.0.0.1:8000/event-bridge",
                "SAP_SANDBOX_WORKFLOW_CALLBACK_URL": "http://127.0.0.1:8000",
            },
        ),
        Service(
            name="ChainMind API",
            command=(
                python,
                "-m",
                "uvicorn",
                "chainmind.api.main:app",
                "--app-dir",
                "src",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ),
            cwd=root,
            health_url="http://127.0.0.1:8000/health",
            environment=common_env,
        ),
        Service(
            name="Dashboard",
            command=dashboard_command,
            cwd=root / "dashboard",
            health_url="http://127.0.0.1:5173/",
            environment={
                "VITE_API_URL": "http://127.0.0.1:8000",
                "VITE_OIDC_ISSUER": "http://127.0.0.1:8100",
            },
        ),
    )


def _start(service: Service, base_environment: dict[str, str]) -> subprocess.Popen[bytes]:
    environment = {**base_environment, **service.environment}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        service.command,
        cwd=service.cwd,
        env=environment,
        creationflags=flags,
    )
    print(f"Starting {service.name} (PID {process.pid})")
    return process


def _wait_until_ready(
    service: Service,
    process: subprocess.Popen[bytes],
    timeout: float = 60,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{service.name} exited with status {process.returncode} before becoming ready."
            )
        try:
            with urlopen(service.health_url, timeout=2) as response:
                if 200 <= response.status < 300:
                    print(f"{service.name} ready: {service.health_url}")
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(f"{service.name} was not ready at {service.health_url}: {last_error}")


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        except OSError:
            process.terminate()
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    """Start processes, wait for health, and stop all child processes on exit."""

    if os.environ.get("CHAINMIND_PREFLIGHT_DONE") != "1":
        preflight = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "preflight.py")],
            cwd=ROOT,
            check=False,
        )
        if preflight.returncode != 0:
            return preflight.returncode
    services = service_definitions()
    processes: list[subprocess.Popen[bytes]] = []
    environment = os.environ.copy()
    stop_requested = Event()
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda signum, frame: stop_requested.set())
    try:
        for service in services:
            process = _start(service, environment)
            processes.append(process)
            _wait_until_ready(service, process)
        print("\nChainMind demo is ready.")
        print("Dashboard: http://127.0.0.1:5173")
        print("API docs:  http://127.0.0.1:8000/docs")
        print("Sandbox:   http://127.0.0.1:8100/docs")
        print("Demo login: approver / demo (or viewer / demo)")
        print("Press Ctrl+C to stop all services.")
        while not stop_requested.wait(1):
            for service, process in zip(services, processes, strict=True):
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{service.name} exited unexpectedly with status {process.returncode}."
                    )
        print("\nStopping local ChainMind services...")
        return 0
    except KeyboardInterrupt:
        print("\nStopping local ChainMind services...")
        return 0
    except (RuntimeError, TimeoutError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        _stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
