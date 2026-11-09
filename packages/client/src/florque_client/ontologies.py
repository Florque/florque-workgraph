"""Registry of ontology extensions per tenant and project (SQLite file, numbered migrations).

The base ontology ships with florque-workgraph-domain. Tenants (and single projects) add
extensions on top of it; a project's effective ontology is base + the tenant's active
extensions + the project's active extensions, in creation order.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE ontology_extensions (
          id TEXT PRIMARY KEY,
          tenant_id TEXT NOT NULL,
          project_key TEXT NOT NULL DEFAULT '',
          name TEXT NOT NULL,
          version TEXT NOT NULL,
          yaml TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL,
          created_by TEXT NOT NULL,
          retired_at TEXT,
          UNIQUE (tenant_id, project_key, name, version)
        );
        CREATE INDEX ontology_extensions_scope
          ON ontology_extensions (tenant_id, project_key, status);
        """,
    )
]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class RegistryConflict(Exception):
    """The same extension name and version already exists in this scope."""


class SQLiteOntologyRegistry:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {r[0] for r in self._db.execute("SELECT version FROM schema_migrations")}
            for version, sql in MIGRATIONS:
                if version in done:
                    continue
                self._db.executescript(
                    f"BEGIN; {sql}; INSERT INTO schema_migrations VALUES ({version}, '{_now()}'); COMMIT;"
                )

    @staticmethod
    def _out(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        d["project_id"] = d.pop("project_key") or None
        return d

    def add(
        self,
        tenant_id: str,
        project_id: str | None,
        name: str,
        version: str,
        text: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Store an extension as active, retiring the previous active version of the same name."""
        row_id = f"ext_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "UPDATE ontology_extensions SET status = 'retired', retired_at = ? "
                    "WHERE tenant_id = ? AND project_key = ? AND name = ? AND status = 'active'",
                    (now, tenant_id, project_id or "", name),
                )
                self._db.execute(
                    "INSERT INTO ontology_extensions "
                    "(id, tenant_id, project_key, name, version, yaml, status, created_at, created_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                    (row_id, tenant_id, project_id or "", name, version, text, now, actor_id),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as e:
                self._db.execute("ROLLBACK")
                raise RegistryConflict(f"{name}@{version} already exists") from e
        got = self.get(row_id)
        assert got is not None
        return got

    def get(self, ext_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._db.execute(
                "SELECT * FROM ontology_extensions WHERE id = ?", (ext_id,)
            ).fetchone()
        return self._out(r) if r else None

    def active(self, tenant_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
        """Effective extensions: the tenant's, then the project's, oldest first."""
        keys = ["", project_id] if project_id else [""]
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM ontology_extensions WHERE tenant_id = ? AND status = 'active' "
                f"AND project_key IN ({', '.join('?' for _ in keys)}) "
                "ORDER BY project_key <> '', created_at, id",
                (tenant_id, *keys),
            ).fetchall()
        return [self._out(r) for r in rows]

    def list(
        self, tenant_id: str, project_id: str | None = None, include_retired: bool = False
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ontology_extensions WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if project_id is not None:
            sql += " AND project_key IN ('', ?)"
            params.append(project_id)
        if not include_retired:
            sql += " AND status = 'active'"
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY created_at, id", params).fetchall()
        return [self._out(r) for r in rows]

    def retire(self, ext_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE ontology_extensions SET status = 'retired', retired_at = ? "
                "WHERE id = ? AND status = 'active'",
                (_now(), ext_id),
            )
        return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()
