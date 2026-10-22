"""Retry policy behavior for transient integration errors."""

import pytest

import chainmind.core.retry as retry_module
from chainmind.core.errors import IntegrationError
from chainmind.core.retry import retry_integration_call


def test_integration_call_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []

    def flaky_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise IntegrationError("Temporary service failure.")
        return "success"

    monkeypatch.setattr(retry_module.time, "sleep", delays.append)

    result = retry_integration_call(
        flaky_operation,
        attempts=3,
        base_delay_seconds=0.25,
    )

    assert result == "success"
    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_integration_call_reports_final_transient_failure() -> None:
    def unavailable() -> None:
        raise IntegrationError("Service unavailable.")

    with pytest.raises(IntegrationError, match="Service unavailable"):
        retry_integration_call(
            unavailable,
            attempts=2,
            base_delay_seconds=0,
        )
