"""SQLite persistence for searches, plans, and resumable imports."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .exceptions import InvalidPlan
from .models import LiteratureRecord, OperationState, PlanKind, PlanState, SearchSpec

SCHEMA_VERSION = 1


class Ledger:
    """Application-owned SQLite ledger; one connection per transaction."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit a short transaction or roll it back on any exception."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the versioned schema without modifying Zotero's database."""
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_sessions (
                    id TEXT PRIMARY KEY,
                    spec_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT,
                    doi TEXT,
                    title_key TEXT NOT NULL,
                    first_author_key TEXT NOT NULL,
                    year INTEGER,
                    fingerprint TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_doi_idx ON records(doi);
                CREATE INDEX IF NOT EXISTS records_title_idx
                    ON records(title_key, first_author_key, year);
                CREATE TABLE IF NOT EXISTS session_records (
                    session_id TEXT NOT NULL REFERENCES search_sessions(id),
                    record_id TEXT NOT NULL REFERENCES records(id),
                    rank INTEGER NOT NULL,
                    PRIMARY KEY(session_id, record_id)
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    server_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    committed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES plans(id),
                    record_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operations_plan_idx ON operations(plan_id);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(12)}"

    def create_session(self, spec: SearchSpec, source: str = "cnki") -> str:
        session_id = self._new_id("ses")
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO search_sessions(id, spec_json, source, created_at) VALUES(?, ?, ?, ?)",
                (session_id, spec.model_dump_json(), source, datetime.now(UTC).isoformat()),
            )
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM search_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown search session: {session_id}")
        return {
            "id": row["id"],
            "spec": json.loads(row["spec_json"]),
            "source": row["source"],
            "created_at": row["created_at"],
        }

    def upsert_record(self, record: LiteratureRecord) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO records(
                    id, source, source_id, doi, title_key, first_author_key, year,
                    fingerprint, data_json, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_id = excluded.source_id,
                    doi = excluded.doi,
                    title_key = excluded.title_key,
                    first_author_key = excluded.first_author_key,
                    year = excluded.year,
                    fingerprint = excluded.fingerprint,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.id,
                    record.source,
                    record.source_id,
                    record.doi,
                    record.title_key,
                    record.first_author_key,
                    record.year,
                    record.fingerprint,
                    record.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def add_session_records(self, session_id: str, records: list[LiteratureRecord]) -> None:
        with self.transaction() as connection:
            for rank, record in enumerate(records, start=1):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO session_records(session_id, record_id, rank)
                    VALUES(?, ?, ?)
                    """,
                    (session_id, record.id, rank),
                )

    def get_record(self, record_id: str) -> LiteratureRecord:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT data_json FROM records WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown literature record: {record_id}")
        return LiteratureRecord.model_validate_json(row["data_json"])

    def get_records(
        self,
        *,
        session_id: str | None = None,
        record_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[LiteratureRecord]:
        if session_id is None and not record_ids:
            raise ValueError("session_id or record_ids is required")
        with self.transaction() as connection:
            if session_id is not None:
                rows = connection.execute(
                    """
                    SELECT r.data_json
                    FROM session_records sr
                    JOIN records r ON r.id = sr.record_id
                    WHERE sr.session_id = ?
                    ORDER BY sr.rank
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                selected = (record_ids or [])[:limit]
                placeholders = ",".join("?" for _ in selected)
                if not placeholders:
                    return []
                rows = connection.execute(
                    f"SELECT data_json FROM records WHERE id IN ({placeholders})",
                    selected,
                ).fetchall()
        return [LiteratureRecord.model_validate_json(row["data_json"]) for row in rows]

    def create_plan(
        self,
        kind: PlanKind,
        payload: dict[str, Any],
        *,
        ttl_minutes: int,
        server_id: str | None = None,
    ) -> tuple[str, str, datetime]:
        """Persist a mutation plan and return its one-time confirmation token."""
        plan_id = self._new_id("plan")
        token = secrets.token_urlsafe(18)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl_minutes)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO plans(
                    id, kind, state, token_hash, payload_json, server_id,
                    created_at, expires_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    kind.value,
                    PlanState.PLANNED.value,
                    token_hash,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    server_id,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return plan_id, token, expires_at

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise InvalidPlan(f"unknown plan: {plan_id}")
        return {
            "id": row["id"],
            "kind": row["kind"],
            "state": row["state"],
            "payload": json.loads(row["payload_json"]),
            "server_id": row["server_id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    def confirm_plan(
        self,
        plan_id: str,
        token: str,
        expected_kind: PlanKind,
        *,
        operation_specs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Consume a plan and optionally create all recovery rows atomically."""
        now = datetime.now(UTC)
        operation_ids: list[str] = []
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                raise InvalidPlan(f"unknown plan: {plan_id}")
            if row["kind"] != expected_kind.value:
                raise InvalidPlan(f"plan {plan_id} is not a {expected_kind.value} plan")
            if row["state"] != PlanState.PLANNED.value:
                raise InvalidPlan(f"plan {plan_id} is already {row['state']}")
            expires_at = datetime.fromisoformat(row["expires_at"])
            if now > expires_at:
                connection.execute(
                    "UPDATE plans SET state = ? WHERE id = ?",
                    (PlanState.EXPIRED.value, plan_id),
                )
                # Preserve the terminal expiration state before raising. The
                # surrounding context's rollback then has nothing left to undo.
                connection.commit()
                raise InvalidPlan(f"plan {plan_id} has expired")
            actual_hash = hashlib.sha256(token.encode()).hexdigest()
            if not hmac.compare_digest(actual_hash, row["token_hash"]):
                raise InvalidPlan("confirmation token does not match the plan")
            connection.execute(
                "UPDATE plans SET state = ?, committed_at = ? WHERE id = ?",
                (PlanState.COMMITTED.value, now.isoformat(), plan_id),
            )
            payload = json.loads(row["payload_json"])
            for spec in operation_specs or []:
                operation_id = self._new_id("op")
                operation_ids.append(operation_id)
                operation_payload = spec.get("payload")
                if not isinstance(operation_payload, dict):
                    raise ValueError("operation spec payload must be a mapping")
                connection.execute(
                    """
                    INSERT INTO operations(
                        id, plan_id, record_id, mode, state, payload_json,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        plan_id,
                        str(spec["record_id"]),
                        str(spec["mode"]),
                        OperationState.PLANNED.value,
                        json.dumps(operation_payload, ensure_ascii=False, sort_keys=True),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
        return {
            "id": plan_id,
            "kind": row["kind"],
            "payload": payload,
            "server_id": row["server_id"],
            "operation_ids": operation_ids,
        }

    def create_operation(
        self,
        plan_id: str,
        record_id: str,
        mode: str,
        payload: dict[str, Any],
    ) -> str:
        operation_id = self._new_id("op")
        now = datetime.now(UTC).isoformat()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO operations(
                    id, plan_id, record_id, mode, state, payload_json,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    plan_id,
                    record_id,
                    mode,
                    OperationState.PLANNED.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return operation_id

    def update_operation(
        self,
        operation_id: str,
        state: OperationState,
        *,
        payload_updates: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown operation: {operation_id}")
            payload = json.loads(row["payload_json"])
            payload.update(payload_updates or {})
            connection.execute(
                """
                UPDATE operations
                SET state = ?, payload_json = ?, error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(error, ensure_ascii=False, sort_keys=True) if error else None,
                    datetime.now(UTC).isoformat(),
                    operation_id,
                ),
            )
        return self.get_operation(operation_id)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE id = ?", (operation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown operation: {operation_id}")
        return {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "record_id": row["record_id"],
            "mode": row["mode"],
            "state": row["state"],
            "payload": json.loads(row["payload_json"]),
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_operations(self, plan_id: str) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT id FROM operations WHERE plan_id = ? ORDER BY created_at", (plan_id,)
            ).fetchall()
        return [self.get_operation(row["id"]) for row in rows]


__all__ = ["SCHEMA_VERSION", "Ledger"]
