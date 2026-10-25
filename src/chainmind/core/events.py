"""In-memory event/run store used by the local demo."""

import sqlite3
from pathlib import Path
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

    def get_by_idempotency_key(self, key: str, tenant_id: str = "demo") -> DisruptionRun | None:
        """Retrieve the existing run for an already processed event key."""

    def list(self) -> list[DisruptionRun]:
        """Return run snapshots newest first."""


class EventStore:
    """Thread-safe local run store; replaceable by DynamoDB in AWS deployments."""

    def __init__(self) -> None:
        self._runs: dict[UUID, DisruptionRun] = {}
        self._keys: dict[tuple[str, str], UUID] = {}
        self._lock = RLock()

    def save(self, run: DisruptionRun) -> None:
        """Persist or update a run snapshot."""

        with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)
            self._keys[(run.tenant_id, run.event.dedupe_key)] = run.run_id

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

    def get_by_idempotency_key(self, key: str, tenant_id: str = "demo") -> DisruptionRun | None:
        """Retrieve a run by its external-event idempotency key."""

        with self._lock:
            run_id = self._keys.get((tenant_id, key))
            run = self._runs.get(run_id) if run_id else None
            return run.model_copy(deep=True) if run else None


class SQLiteEventStore:
    """SQLite-backed local event/run store with a unique idempotency index."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        path = Path(database_path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    run_data TEXT NOT NULL
                )
                """
            )
            rows = self._connection.execute(
                "SELECT run_id, idempotency_key, run_data FROM runs"
            ).fetchall()
            for row in rows:
                run = DisruptionRun.model_validate_json(row["run_data"])
                scoped_key = _idempotency_storage_key(run.event.dedupe_key, run.tenant_id)
                if row["idempotency_key"] != scoped_key:
                    self._connection.execute(
                        "UPDATE runs SET idempotency_key = ? WHERE run_id = ?",
                        (scoped_key, row["run_id"]),
                    )

    def save(self, run: DisruptionRun) -> None:
        """Persist or update a JSON-serialized run snapshot."""

        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (run_id, created_at, idempotency_key, run_data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    idempotency_key = excluded.idempotency_key,
                    run_data = excluded.run_data
                """,
                (
                    str(run.run_id),
                    run.created_at.isoformat(),
                    _idempotency_storage_key(run.event.dedupe_key, run.tenant_id),
                    run.model_dump_json(),
                ),
            )

    def get(self, run_id: UUID) -> DisruptionRun | None:
        """Retrieve and validate one stored run."""

        with self._lock:
            row = self._connection.execute(
                "SELECT run_data FROM runs WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        return DisruptionRun.model_validate_json(row["run_data"]) if row else None

    def get_by_idempotency_key(self, key: str, tenant_id: str = "demo") -> DisruptionRun | None:
        """Retrieve an existing run using its unique event key."""

        with self._lock:
            row = self._connection.execute(
                "SELECT run_data FROM runs WHERE idempotency_key = ?",
                (_idempotency_storage_key(key, tenant_id),),
            ).fetchone()
        return DisruptionRun.model_validate_json(row["run_data"]) if row else None

    def list(self) -> list[DisruptionRun]:
        """Return stored runs newest first."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT run_data FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [DisruptionRun.model_validate_json(row["run_data"]) for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        with self._lock:
            self._connection.close()


def _idempotency_storage_key(key: str, tenant_id: str) -> str:
    """Scope an otherwise external event key to its owning tenant."""

    return f"{tenant_id}:{key}"
