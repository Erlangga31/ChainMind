"""In-memory event/run store used by the local demo."""

from threading import RLock
from typing import Protocol
from uuid import UUID

from chainmind.core.models import DisruptionRun


class RunStore(Protocol):
    """Storage interface used by the core workflow and transport layer."""

    def save(self, run: DisruptionRun) -> None:
        """Persist or update a run snapshot."""

    def get(self, run_id: UUID) -> DisruptionRun | None:
        """Retrieve one run snapshot."""

    def list(self) -> list[DisruptionRun]:
        """Return run snapshots newest first."""


class EventStore:
    """Thread-safe local run store; replaceable by DynamoDB in AWS deployments."""

    def __init__(self) -> None:
        self._runs: dict[UUID, DisruptionRun] = {}
        self._lock = RLock()

    def save(self, run: DisruptionRun) -> None:
        """Persist or update a run snapshot."""

        with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)

    def get(self, run_id: UUID) -> DisruptionRun | None:
        """Retrieve one run without exposing mutable store state."""

        with self._lock:
            run = self._runs.get(run_id)
            return run.model_copy(deep=True) if run else None

    def list(self) -> list[DisruptionRun]:
        """Return runs newest first."""

        with self._lock:
            return sorted(
                (run.model_copy(deep=True) for run in self._runs.values()),
                key=lambda run: run.created_at,
                reverse=True,
            )
