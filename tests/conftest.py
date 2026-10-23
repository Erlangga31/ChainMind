"""Shared fixtures for local HTTP integration tests."""

from collections.abc import Iterator
from socket import socket
from threading import Thread
from time import monotonic, sleep

import pytest
import uvicorn

from sandbox.sap_sandbox.config import SandboxSettings
from sandbox.sap_sandbox.main import create_app


@pytest.fixture
def sap_sandbox_url() -> Iterator[str]:
    """Run an isolated SAP sandbox HTTP server on an ephemeral local port."""

    listener = socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(
                SandboxSettings(
                    event_webhook_url="http://127.0.0.1:9/disruptions",
                    workflow_callback_url="http://127.0.0.1:9",
                )
            ),
            log_level="error",
        )
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = monotonic() + 10
    try:
        while not server.started and monotonic() < deadline:
            if not thread.is_alive():
                pytest.fail("SAP sandbox server exited during startup.")
            sleep(0.05)
        if not server.started:
            pytest.fail("SAP sandbox server did not become ready.")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        if thread.is_alive():
            pytest.fail("SAP sandbox server did not shut down.")
