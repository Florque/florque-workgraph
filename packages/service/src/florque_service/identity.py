"""Identity: tenants, users, memberships, invites, login codes and API tokens (SQLite).

Tokens look like ``fwg_<id>_<secret>``. Only a SHA-256 of the secret is stored: the secret
is 256 random bits, so a fast hash is safe and keeps per-request verification cheap.

Token kinds
- ``user``: a person or their agent, scoped to one tenant; every member is admin of the
  tenant's projects (no RBAC yet).
- ``ingest``: pushes observations for one tenant (``/v1/hub/observations`` only).
- ``operator``: server operators, issued on the host; carries an explicit role map.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from florque_graph_core import Principal
from florque_graph_core.errors import ErrorCode, GraphError

ROLES = {"admin", "contributor", "viewer", "hub"}
KINDS = {"user", "ingest", "operator"}
USER_TOKEN_DAYS = 90
INGEST_TOKEN_DAYS = 365
INVITE_DAYS = 14
LOGIN_CODE_MINUTES = 10
LOGIN_CODE_ATTEMPTS = 5
TOUCH_SECONDS = 300
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE tenants (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE users (
          id TEXT PRIMARY KEY,
          email TEXT NOT NULL UNIQUE COLLATE NOCASE,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL,
          last_login_at TEXT
        );
        CREATE TABLE memberships (
          user_id TEXT NOT NULL REFERENCES users(id),
          tenant_id TEXT NOT NULL REFERENCES tenants(id),
          role TEXT NOT NULL DEFAULT 'admin',
          created_at TEXT NOT NULL,
          PRIMARY KEY (user_id, tenant_id)
        );
        CREATE TABLE invites (
          id TEXT PRIMARY KEY,
          code_hash TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL COLLATE NOCASE,
          tenant_id TEXT REFERENCES tenants(id),
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          used_at TEXT,
          used_by TEXT
        );
        CREATE TABLE login_codes (
          id TEXT PRIMARY KEY,
          email TEXT NOT NULL COLLATE NOCASE,
          code_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          used_at TEXT
        );
        CREATE INDEX login_codes_email ON login_codes (email, created_at);
        CREATE TABLE api_tokens (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          user_id TEXT REFERENCES users(id),
          tenant_id TEXT REFERENCES tenants(id),
          actor_id TEXT NOT NULL,
          roles TEXT NOT NULL DEFAULT '{}',
          can_create_projects INTEGER NOT NULL DEFAULT 0,
          is_agent INTEGER NOT NULL DEFAULT 0,
          label TEXT,
          hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          last_used_at TEXT,
          revoked_at TEXT
        );
        CREATE INDEX api_tokens_user ON api_tokens (user_id, tenant_id);
        """,
    )
]


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _bad(code: ErrorCode, message: str, hint: str = "") -> GraphError:
    return GraphError(code, message, hint=hint)


@dataclass(frozen=True)
class TokenInfo:
    principal: Principal
    kind: str
    token_id: str
    user_id: str | None
    tenant_id: str | None
    expires_at: str | None
    project_id: str | None = None  # a user token limited to one project


class IdentityStore:
    def __init__(self, path: str = ":memory:", clock: Any = None) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout = 5000")
        self._db.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    # ------------------------------------------------------------------ plumbing

    def _migrate(self) -> None:
        with self._lock:
            tables = {
                r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "api_tokens" in tables and "schema_migrations" not in tables:
                # tokens from v0.1 (argon2, no kinds) cannot be migrated: keep them aside
                self._db.execute("ALTER TABLE api_tokens RENAME TO api_tokens_v0")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {r[0] for r in self._db.execute("SELECT version FROM schema_migrations")}
            for version, sql in MIGRATIONS:
                if version not in done:
                    self._db.executescript(
                        f"BEGIN; {sql} INSERT INTO schema_migrations VALUES "
                        f"({version}, '{self._now()}'); COMMIT;"
                    )

    def _now(self) -> str:
        return _ts(self.clock())

    def _later(self, **delta: float) -> str:
        return _ts(self.clock() + timedelta(**delta))

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._lock:
            r = self._db.execute(sql, params).fetchone()
        return dict(r) if r else None

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._lock:
            return self._db.execute(sql, params).rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ tenants and users

    def create_tenant(self, name: str) -> dict[str, Any]:
        row = {"id": f"tenant_{uuid.uuid4().hex[:12]}", "name": name.strip() or "Workspace"}
        self._exec("INSERT INTO tenants VALUES (?, ?, ?)", (row["id"], row["name"], self._now()))
        return row

    def tenant(self, tenant_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM tenants WHERE id = ?", (tenant_id,))

    def tenants(self) -> list[dict[str, Any]]:
        return self._all(
            "SELECT t.*, (SELECT count(*) FROM memberships m WHERE m.tenant_id = t.id) AS members "
            "FROM tenants t ORDER BY created_at"
        )

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM users WHERE email = ?", (email.strip(),))

    def user(self, user_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM users WHERE id = ?", (user_id,))

    def users(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM users ORDER BY created_at")

    def memberships(self, user_id: str) -> list[dict[str, Any]]:
        return self._all(
            "SELECT m.tenant_id, m.role, t.name AS tenant_name FROM memberships m "
            "JOIN tenants t ON t.id = m.tenant_id WHERE m.user_id = ? ORDER BY m.created_at",
            (user_id,),
        )

    def _add_member(self, user_id: str, tenant_id: str, role: str = "admin") -> None:
        self._exec(
            "INSERT OR IGNORE INTO memberships VALUES (?, ?, ?, ?)",
            (user_id, tenant_id, role, self._now()),
        )

    # ------------------------------------------------------------------ invites

    def create_invite(
        self, email: str, created_by: str, tenant_id: str | None = None, days: int = INVITE_DAYS
    ) -> dict[str, Any]:
        """A one-time, email-bound invite. Without tenant_id it creates a new tenant."""
        email = email.strip()
        if not _EMAIL.match(email):
            raise _bad(ErrorCode.ONTOLOGY_VIOLATION, f"{email!r} is not an email address")
        if tenant_id is not None and self.tenant(tenant_id) is None:
            raise _bad(ErrorCode.NOT_FOUND, f"Tenant {tenant_id!r} not found")
        raw = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(12))
        code = f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"
        row = {
            "id": f"inv_{uuid.uuid4().hex[:12]}",
            "email": email,
            "tenant_id": tenant_id,
            "expires_at": self._later(days=days),
        }
        self._exec(
            "INSERT INTO invites (id, code_hash, email, tenant_id, created_by, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                _sha(code),
                email,
                tenant_id,
                created_by,
                self._now(),
                row["expires_at"],
            ),
        )
        return {**row, "code": code}

    def invites(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        cols = "id, email, tenant_id, created_by, created_at, expires_at, used_at, used_by"
        if tenant_id is None:
            return self._all(f"SELECT {cols} FROM invites ORDER BY created_at")
        return self._all(
            f"SELECT {cols} FROM invites WHERE tenant_id = ? ORDER BY created_at", (tenant_id,)
        )

    def register(
        self,
        code: str,
        email: str,
        name: str,
        tenant_name: str | None = None,
        label: str | None = None,
        is_agent: bool = False,
    ) -> dict[str, Any]:
        """Redeem an invite: create (or join) the tenant and the user, and issue a user token."""
        invite = self._one(
            "SELECT * FROM invites WHERE code_hash = ?", (_sha(code.strip().upper()),)
        )
        now = self._now()
        if invite is None or invite["used_at"] or invite["expires_at"] < now:
            raise _bad(
                ErrorCode.FORBIDDEN,
                "Invite code is invalid, used or expired",
                hint="Ask for a new invite.",
            )
        if invite["email"].lower() != email.strip().lower():
            raise _bad(
                ErrorCode.FORBIDDEN,
                "This invite was issued for another email address",
                hint="Register with the address the invite was sent to.",
            )
        user = self.user_by_email(email)
        if user is not None and invite["tenant_id"] is None:
            raise _bad(
                ErrorCode.DUPLICATE_EXACT,
                f"{email} is already registered",
                hint="Use fwg login instead.",
            )
        if user is None:
            user = {
                "id": f"user_{uuid.uuid4().hex[:12]}",
                "email": email.strip(),
                "name": name.strip() or email.split("@")[0],
            }
            self._exec(
                "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                (user["id"], user["email"], user["name"], now),
            )
        tenant = (
            self.tenant(invite["tenant_id"])
            if invite["tenant_id"]
            else self.create_tenant(tenant_name or f"{user['name']}'s workspace")
        )
        assert tenant is not None
        self._add_member(user["id"], tenant["id"])
        changed = self._exec(
            "UPDATE invites SET used_at = ?, used_by = ? WHERE id = ? AND used_at IS NULL",
            (now, user["id"], invite["id"]),
        )
        if not changed:
            raise _bad(ErrorCode.FORBIDDEN, "Invite code was used concurrently")
        token = self.issue_user_token(user["id"], tenant["id"], label or "cli", is_agent)
        return {
            "user": {k: user[k] for k in ("id", "email", "name")},
            "tenant": {"id": tenant["id"], "name": tenant["name"]},
            **token,
        }

    # ------------------------------------------------------------------ login codes

    def start_login(self, email: str) -> str | None:
        """A fresh 6-digit code for a registered email (older codes stop working)."""
        user = self.user_by_email(email)
        if user is None:
            return None
        code = f"{secrets.randbelow(10**6):06d}"
        now = self._now()
        self._exec(
            "UPDATE login_codes SET used_at = ? WHERE email = ? AND used_at IS NULL",
            (now, user["email"]),
        )
        self._exec(
            "INSERT INTO login_codes (id, email, code_hash, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                user["email"],
                _sha(f"{user['email'].lower()}:{code}"),
                now,
                self._later(minutes=LOGIN_CODE_MINUTES),
            ),
        )
        return code

    def verify_login(
        self,
        email: str,
        code: str,
        label: str | None = None,
        tenant_id: str | None = None,
        is_agent: bool = False,
    ) -> dict[str, Any]:
        user = self.user_by_email(email)
        failure = _bad(
            ErrorCode.UNAUTHENTICATED,
            "Login code is invalid or expired",
            hint="Request a new code with fwg login.",
        )
        if user is None:
            raise failure
        now = self._now()
        row = self._one(
            "SELECT * FROM login_codes WHERE email = ? AND used_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (user["email"],),
        )
        if row is None or row["expires_at"] < now or row["attempts"] >= LOGIN_CODE_ATTEMPTS:
            raise failure
        expected = _sha(f"{user['email'].lower()}:{code.strip()}")
        if not hmac.compare_digest(row["code_hash"], expected):
            self._exec("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
            raise failure
        self._exec("UPDATE login_codes SET used_at = ? WHERE id = ?", (now, row["id"]))
        tenants = self.memberships(user["id"])
        if not tenants:
            raise _bad(ErrorCode.FORBIDDEN, "This account belongs to no tenant")
        chosen = next((t for t in tenants if t["tenant_id"] == tenant_id), None)
        if tenant_id is not None and chosen is None:
            raise _bad(ErrorCode.FORBIDDEN, f"Not a member of tenant {tenant_id!r}")
        chosen = chosen or tenants[0]
        self._exec("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
        token = self.issue_user_token(user["id"], chosen["tenant_id"], label or "cli", is_agent)
        return {
            "user": {k: user[k] for k in ("id", "email", "name")},
            "tenant": {"id": chosen["tenant_id"], "name": chosen["tenant_name"]},
            "tenants": tenants,
            **token,
        }

    # ------------------------------------------------------------------ tokens

    def _insert_token(
        self,
        kind: str,
        actor_id: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        roles: dict[str, str] | None = None,
        can_create_projects: bool = False,
        is_agent: bool = False,
        label: str | None = None,
        days: float | None = None,
    ) -> dict[str, Any]:
        token_id = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        expires_at = self._later(days=days) if days else None
        self._exec(
            "INSERT INTO api_tokens (id, kind, user_id, tenant_id, actor_id, roles, "
            "can_create_projects, is_agent, label, hash, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                token_id,
                kind,
                user_id,
                tenant_id,
                actor_id,
                json.dumps(roles or {}),
                int(can_create_projects),
                int(is_agent),
                label,
                _sha(secret),
                self._now(),
                expires_at,
            ),
        )
        return {
            "token": f"fwg_{token_id}_{secret}",
            "token_id": token_id,
            "kind": kind,
            "expires_at": expires_at,
        }

    def issue_user_token(
        self,
        user_id: str,
        tenant_id: str,
        label: str | None = None,
        is_agent: bool = False,
        days: float = USER_TOKEN_DAYS,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """A user token for the whole tenant, or limited to one project (project_id; the
        caller checks that the project belongs to the tenant)."""
        if not self._one(
            "SELECT 1 FROM memberships WHERE user_id = ? AND tenant_id = ?", (user_id, tenant_id)
        ):
            raise _bad(ErrorCode.FORBIDDEN, "Not a member of this tenant")
        out = self._insert_token(
            "user",
            user_id,
            user_id=user_id,
            tenant_id=tenant_id,
            # for user tokens the roles column holds the project scope; the role itself
            # always comes from the membership, so it follows membership changes
            roles={project_id: "member"} if project_id else None,
            can_create_projects=project_id is None,
            is_agent=is_agent,
            label=label,
            days=days,
        )
        return {**out, "project_id": project_id}

    def issue_ingest_token(
        self,
        tenant_id: str,
        created_by: str,
        label: str | None = None,
        days: float = INGEST_TOKEN_DAYS,
    ) -> dict[str, Any]:
        return self._insert_token(
            "ingest",
            f"ingest:{created_by}",
            user_id=created_by if created_by.startswith("user_") else None,
            tenant_id=tenant_id,
            is_agent=True,
            label=label,
            days=days,
        )

    def issue(
        self,
        actor_id: str,
        roles: dict[str, str],
        can_create_projects: bool = False,
        is_agent: bool = False,
        label: str | None = None,
        days: float | None = None,
    ) -> dict[str, Any]:
        """An operator token with an explicit role map (``*`` = every project, every tenant)."""
        bad = {r for r in roles.values() if r not in ROLES}
        if bad:
            raise ValueError(f"unknown role(s) {sorted(bad)}; use {sorted(ROLES)}")
        out = self._insert_token(
            "operator",
            actor_id,
            roles=roles,
            can_create_projects=can_create_projects,
            is_agent=is_agent,
            label=label,
            days=days,
        )
        return {**out, "id": out["token_id"], "actor_id": actor_id, "roles": roles}

    def resolve(self, token: str) -> TokenInfo | None:
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != "fwg":
            return None
        _, token_id, secret = parts
        row = self._one("SELECT * FROM api_tokens WHERE id = ? AND revoked_at IS NULL", (token_id,))
        if row is None or not hmac.compare_digest(row["hash"], _sha(secret)):
            return None
        now = self._now()
        if row["expires_at"] and row["expires_at"] < now:
            return None
        if row["last_used_at"] is None or row["last_used_at"] < _ts(
            self.clock() - timedelta(seconds=TOUCH_SECONDS)
        ):
            self._exec("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now, token_id))
        if row["kind"] == "operator":
            p = Principal(
                actor_id=row["actor_id"],
                roles=json.loads(row["roles"]),
                can_create_projects=bool(row["can_create_projects"]),
                is_agent=bool(row["is_agent"]),
            )
        elif row["kind"] == "ingest":
            p = Principal(
                actor_id=row["actor_id"],
                roles={"*": "hub"},
                is_agent=True,
                tenant_id=row["tenant_id"],
            )
        else:
            member = self._one(
                "SELECT role FROM memberships WHERE user_id = ? AND tenant_id = ?",
                (row["user_id"], row["tenant_id"]),
            )
            if member is None:
                return None  # removed from the tenant
            scope = list(json.loads(row["roles"] or "{}"))
            project_id = scope[0] if scope else None
            p = Principal(
                actor_id=row["user_id"],
                roles={project_id or "*": member["role"]},
                is_agent=bool(row["is_agent"]),
                can_create_projects=project_id is None,
                tenant_id=row["tenant_id"],
            )
            return TokenInfo(
                p,
                row["kind"],
                token_id,
                row["user_id"],
                row["tenant_id"],
                row["expires_at"],
                project_id,
            )
        return TokenInfo(
            p, row["kind"], token_id, row["user_id"], row["tenant_id"], row["expires_at"]
        )

    def principal(self, token: str) -> Principal | None:
        info = self.resolve(token)
        return info.principal if info else None

    def tokens(
        self, user_id: str | None = None, tenant_id: str | None = None
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, kind, user_id, tenant_id, actor_id, roles, can_create_projects, is_agent, "
            "label, created_at, expires_at, last_used_at, revoked_at FROM api_tokens"
        )
        conds, params = [], []
        if user_id is not None:
            conds.append("user_id = ?")
            params.append(user_id)
        if tenant_id is not None:
            conds.append("tenant_id = ?")
            params.append(tenant_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        rows = self._all(sql + " ORDER BY created_at", tuple(params))
        for r in rows:
            r["roles"] = json.loads(r["roles"])
            r["can_create_projects"] = bool(r["can_create_projects"])
            r["is_agent"] = bool(r["is_agent"])
        return rows

    def list(self) -> list[dict[str, Any]]:
        return self.tokens()

    def revoke(self, token_id: str, tenant_id: str | None = None) -> bool:
        if tenant_id is None:
            return (
                self._exec(
                    "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (self._now(), token_id),
                )
                > 0
            )
        return (
            self._exec(
                "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND tenant_id = ? "
                "AND revoked_at IS NULL",
                (self._now(), token_id, tenant_id),
            )
            > 0
        )
