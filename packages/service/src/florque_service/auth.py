"""Bearer tokens, stored hashed (argon2), each bound to an Actor and per-project roles (spec 7)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from florque_graph_core import Principal

ROLES = {"admin", "contributor", "viewer", "hub"}
_ph = PasswordHasher()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TokenStore:
    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS api_tokens ("
            " id TEXT PRIMARY KEY, prefix TEXT NOT NULL, hash TEXT NOT NULL, actor_id TEXT NOT NULL,"
            " roles TEXT NOT NULL, can_create_projects INTEGER NOT NULL DEFAULT 0, is_agent INTEGER NOT NULL DEFAULT 0,"
            " label TEXT, created_at TEXT NOT NULL, revoked_at TEXT)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS api_tokens_prefix ON api_tokens (prefix)")

    def issue(
        self,
        actor_id: str,
        roles: dict[str, str],
        can_create_projects: bool = False,
        is_agent: bool = False,
        label: str | None = None,
    ) -> dict[str, Any]:
        bad = {r for r in roles.values() if r not in ROLES}
        if bad:
            raise ValueError(f"unknown role(s) {sorted(bad)}; use {sorted(ROLES)}")
        token_id = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        token = f"fwg_{token_id}_{secret}"
        with self._lock:
            self._db.execute(
                "INSERT INTO api_tokens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    token_id,
                    token_id,
                    _ph.hash(secret),
                    actor_id,
                    json.dumps(roles),
                    int(can_create_projects),
                    int(is_agent),
                    label,
                    _now(),
                ),
            )
        return {"id": token_id, "token": token, "actor_id": actor_id, "roles": roles}

    def revoke(self, token_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (_now(), token_id),
            )
            return cur.rowcount > 0

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, actor_id, roles, can_create_projects, is_agent, label, created_at, revoked_at FROM api_tokens"
            ).fetchall()
        return [
            {
                "id": r[0],
                "actor_id": r[1],
                "roles": json.loads(r[2]),
                "can_create_projects": bool(r[3]),
                "is_agent": bool(r[4]),
                "label": r[5],
                "created_at": r[6],
                "revoked_at": r[7],
            }
            for r in rows
        ]

    def principal(self, token: str) -> Principal | None:
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != "fwg":
            return None
        _, token_id, secret = parts
        with self._lock:
            row = self._db.execute(
                "SELECT hash, actor_id, roles, can_create_projects, is_agent FROM api_tokens "
                "WHERE prefix = ? AND revoked_at IS NULL",
                (token_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            _ph.verify(row[0], secret)
        except VerifyMismatchError:
            return None
        return Principal(
            actor_id=row[1],
            roles=json.loads(row[2]),
            can_create_projects=bool(row[3]),
            is_agent=bool(row[4]),
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()
