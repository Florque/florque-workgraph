"""SQLite hub store in WAL mode with numbered migrations and lease-based job claiming."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any

from florque_signal_hub.store.repository import Row, StoreConflict

BINDING_TABLES = {"channel": "channel_bindings", "thread": "thread_bindings"}
JSON_COLUMNS = {"config", "envelope", "candidates", "detail", "payload", "resolution"}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _row(cur: sqlite3.Cursor, r: tuple[Any, ...]) -> Row:
    out: Row = {}
    for col, v in zip((d[0] for d in cur.description), r, strict=True):
        if col in JSON_COLUMNS and isinstance(v, str):
            with contextlib.suppress(ValueError):
                v = json.loads(v)
        out[col] = v
    return out


def migrations() -> list[tuple[int, str]]:
    pkg = resources.files("florque_signal_hub.store") / "migrations"
    out = []
    for f in pkg.iterdir():
        if f.name.endswith(".sql"):
            out.append((int(f.name.split("_", 1)[0]), f.read_text()))
    return sorted(out)


class SQLiteHubStore:
    def __init__(self, path: str = ":memory:", tenant_id: str = "default") -> None:
        self.tenant_id = tenant_id
        self.path = path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    # ------------------------------------------------------------------ plumbing

    def migrate(self) -> list[int]:
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {r[0] for r in self._db.execute("SELECT version FROM schema_migrations")}
            applied = []
            for version, sql in migrations():
                if version in done:
                    continue
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in (s.strip() for s in sql.split(";")):
                        if stmt and not all(
                            line.startswith("--") for line in stmt.splitlines() if line.strip()
                        ):
                            self._db.execute(stmt)
                    self._db.execute(
                        "INSERT INTO schema_migrations VALUES (?, ?)", (version, _now())
                    )
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
                applied.append(version)
            return applied

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self._db.execute(sql, params)
            except sqlite3.IntegrityError as e:
                raise StoreConflict(str(e)) from e

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> Row | None:
        with self._lock:
            cur = self._db.execute(sql, params)
            r = cur.fetchone()
            return _row(cur, r) if r else None

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[Row]:
        with self._lock:
            cur = self._db.execute(sql, params)
            return [_row(cur, r) for r in cur.fetchall()]

    def _insert(self, table: str, row: Row) -> Row:
        row = {"tenant_id": self.tenant_id, **row}
        cols = ", ".join(row)
        qs = ", ".join("?" for _ in row)
        vals = tuple(
            json.dumps(v) if k in JSON_COLUMNS and not isinstance(v, str) else v
            for k, v in row.items()
        )
        self._exec(f"INSERT INTO {table} ({cols}) VALUES ({qs})", vals)
        return {k: v for k, v in row.items()}

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ registry

    def add_source(self, id: str, kind: str, name: str | None, config: dict[str, Any]) -> Row:
        return self._insert(
            "sources",
            {"id": id, "kind": kind, "name": name, "config": config, "created_at": _now()},
        )

    def get_source(self, id: str) -> Row | None:
        return self._one(
            "SELECT * FROM sources WHERE tenant_id = ? AND id = ? AND archived_at IS NULL",
            (self.tenant_id, id),
        )

    def list_sources(self) -> list[Row]:
        return self._all(
            "SELECT * FROM sources WHERE tenant_id = ? AND archived_at IS NULL ORDER BY id",
            (self.tenant_id,),
        )

    def archive_source(self, id: str) -> bool:
        cur = self._exec(
            "UPDATE sources SET archived_at = ? WHERE tenant_id = ? AND id = ? AND archived_at IS NULL",
            (_now(), self.tenant_id, id),
        )
        return cur.rowcount > 0

    def add_sensor(self, row: Row) -> Row:
        return self._insert("sensors", {"id": _id("sensor"), "created_at": _now(), **row})

    def sensor_by_code(self, series_code: str) -> Row | None:
        return self._one(
            "SELECT * FROM sensors WHERE tenant_id = ? AND series_code = ? AND archived_at IS NULL",
            (self.tenant_id, series_code),
        )

    def list_sensors(
        self, project_id: str | None = None, include_archived: bool = False
    ) -> list[Row]:
        sql = "SELECT * FROM sensors WHERE tenant_id = ?"
        params: list[Any] = [self.tenant_id]
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        if not include_archived:
            sql += " AND archived_at IS NULL"
        return self._all(sql + " ORDER BY series_code", tuple(params))

    def archive_sensor(self, id: str) -> bool:
        # The unique series_code key spans archived rows, so free the code on archive.
        cur = self._exec(
            "UPDATE sensors SET archived_at = ?, series_code = series_code || '#archived:' || id "
            "WHERE tenant_id = ? AND id = ? AND archived_at IS NULL",
            (_now(), self.tenant_id, id),
        )
        return cur.rowcount > 0

    def flag_sensor(self, id: str, flag: str | None) -> None:
        self._exec(
            "UPDATE sensors SET flag = ? WHERE tenant_id = ? AND id = ?", (flag, self.tenant_id, id)
        )

    def add_binding(self, kind: str, row: Row) -> Row:
        return self._insert(BINDING_TABLES[kind], {"id": _id(kind), "created_at": _now(), **row})

    def list_bindings(self, kind: str, include_archived: bool = False) -> list[Row]:
        sql = f"SELECT * FROM {BINDING_TABLES[kind]} WHERE tenant_id = ?"
        if not include_archived:
            sql += " AND archived_at IS NULL"
        return self._all(sql, (self.tenant_id,))

    def archive_binding(self, kind: str, id: str, flag: str | None = None) -> bool:
        cur = self._exec(
            f"UPDATE {BINDING_TABLES[kind]} SET archived_at = ?, flag = ? WHERE tenant_id = ? AND id = ? AND archived_at IS NULL",
            (_now(), flag, self.tenant_id, id),
        )
        return cur.rowcount > 0

    # ------------------------------------------------------------------ ledger and inbox

    def ledger_insert(self, source_id: str, external_id: str, envelope: dict[str, Any]) -> Row:
        return self._insert(
            "observation_ledger",
            {
                "id": _id("obs"),
                "source_id": source_id,
                "external_id": external_id,
                "received_at": _now(),
                "envelope": envelope,
                "status": "received",
            },
        )

    def ledger_get(self, source_id: str, external_id: str) -> Row | None:
        return self._one(
            "SELECT * FROM observation_ledger WHERE tenant_id = ? AND source_id = ? AND external_id = ?",
            (self.tenant_id, source_id, external_id),
        )

    def ledger_update(
        self, id: str, status: str, signal_id: str | None = None, detail: str | None = None
    ) -> None:
        self._exec(
            "UPDATE observation_ledger SET status = ?, signal_id = coalesce(?, signal_id), detail = ? "
            "WHERE tenant_id = ? AND id = ?",
            (status, signal_id, detail, self.tenant_id, id),
        )

    def inbox_add(
        self, ledger_id: str | None, reason: str, envelope: dict[str, Any], candidates: list[Any]
    ) -> Row:
        return self._insert(
            "inbox",
            {
                "id": _id("inbox"),
                "ledger_id": ledger_id,
                "reason": reason,
                "envelope": envelope,
                "candidates": candidates,
                "status": "open",
                "created_at": _now(),
            },
        )

    def inbox_list(self, status: str | None = "open") -> list[Row]:
        if status:
            return self._all(
                "SELECT * FROM inbox WHERE tenant_id = ? AND status = ? ORDER BY created_at",
                (self.tenant_id, status),
            )
        return self._all(
            "SELECT * FROM inbox WHERE tenant_id = ? ORDER BY created_at", (self.tenant_id,)
        )

    def inbox_get(self, id: str) -> Row | None:
        return self._one("SELECT * FROM inbox WHERE tenant_id = ? AND id = ?", (self.tenant_id, id))

    def inbox_resolve(self, id: str, resolution: str, actor_id: str) -> None:
        self._exec(
            "UPDATE inbox SET status = 'resolved', resolution = ?, resolved_at = ?, resolved_by = ? "
            "WHERE tenant_id = ? AND id = ?",
            (json.dumps(resolution), _now(), actor_id, self.tenant_id, id),
        )

    def match_feedback_add(
        self, inbox_id: str, node_id: str | None, verdict: str, actor_id: str
    ) -> None:
        self._insert(
            "match_feedback",
            {
                "id": _id("mf"),
                "inbox_id": inbox_id,
                "node_id": node_id,
                "verdict": verdict,
                "actor_id": actor_id,
                "created_at": _now(),
            },
        )

    # ------------------------------------------------------------------ audit and events

    def audit(
        self, actor_id: str, action: str, subject: str | None, detail: dict[str, Any]
    ) -> None:
        self._insert(
            "audit_log",
            {
                "id": _id("audit"),
                "at": _now(),
                "actor_id": actor_id,
                "action": action,
                "subject": subject,
                "detail": detail,
            },
        )

    def audit_list(self, limit: int = 100, action: str | None = None) -> list[Row]:
        if action:
            return self._all(
                "SELECT * FROM audit_log WHERE tenant_id = ? AND action = ? ORDER BY at DESC LIMIT ?",
                (self.tenant_id, action, limit),
            )
        return self._all(
            "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY at DESC LIMIT ?",
            (self.tenant_id, limit),
        )

    def event_add(
        self, type: str, node_id: str | None, origin: str, payload: dict[str, Any]
    ) -> Row:
        return self._insert(
            "events",
            {
                "id": _id("evt"),
                "at": _now(),
                "type": type,
                "node_id": node_id,
                "origin": origin,
                "payload": payload,
            },
        )

    def events_since(self, since: str | None, limit: int = 100) -> list[Row]:
        return self._all(
            "SELECT * FROM events WHERE tenant_id = ? AND (? IS NULL OR at > ?) ORDER BY at LIMIT ?",
            (self.tenant_id, since, since, limit),
        )

    # ------------------------------------------------------------------ jobs

    def enqueue(self, kind: str, payload: dict[str, Any], run_after: str | None = None) -> Row:
        now = _now()
        return self._insert(
            "jobs",
            {
                "id": _id("job"),
                "kind": kind,
                "payload": payload,
                "status": "queued",
                "run_after": run_after or now,
                "created_at": now,
                "updated_at": now,
            },
        )

    def claim(self, worker_id: str, lease_seconds: int) -> Row | None:
        now = datetime.now(UTC)
        now_s = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        until = (now + timedelta(seconds=lease_seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        return self._one(
            "UPDATE jobs SET status = 'running', locked_until = ?, worker_id = ?, attempts = attempts + 1, updated_at = ? "
            "WHERE tenant_id = ? AND id = (SELECT id FROM jobs WHERE tenant_id = ? AND "
            "((status = 'queued' AND run_after <= ?) OR (status = 'running' AND locked_until < ?)) "
            "ORDER BY run_after LIMIT 1) RETURNING *",
            (until, worker_id, now_s, self.tenant_id, self.tenant_id, now_s, now_s),
        )

    def complete(self, job_id: str) -> None:
        self._exec(
            "UPDATE jobs SET status = 'done', locked_until = NULL, updated_at = ? WHERE tenant_id = ? AND id = ?",
            (_now(), self.tenant_id, job_id),
        )

    def fail(self, job_id: str, error: str, retry_after_seconds: int | None) -> None:
        if retry_after_seconds is None:
            self._exec(
                "UPDATE jobs SET status = 'failed', last_error = ?, locked_until = NULL, updated_at = ? WHERE tenant_id = ? AND id = ?",
                (error, _now(), self.tenant_id, job_id),
            )
        else:
            run_after = (datetime.now(UTC) + timedelta(seconds=retry_after_seconds)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            self._exec(
                "UPDATE jobs SET status = 'queued', last_error = ?, locked_until = NULL, run_after = ?, updated_at = ? "
                "WHERE tenant_id = ? AND id = ?",
                (error, run_after, _now(), self.tenant_id, job_id),
            )
