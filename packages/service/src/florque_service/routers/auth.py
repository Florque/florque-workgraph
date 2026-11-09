"""Registration, login and token management (/v1/auth). Users never set passwords:
an emailed invite registers them, an emailed one-time code logs them in on a new device."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from florque_graph_core.errors import ErrorCode, GraphError
from pydantic import BaseModel, Field

from florque_service.email import EmailError, invite_email, login_email
from florque_service.identity import TokenInfo
from florque_service.state import ServiceState, respond, state, user_info

router = APIRouter(prefix="/v1/auth")
log = logging.getLogger("florque.auth")


class RegisterBody(BaseModel):
    invite_code: str = Field(min_length=4, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(default="", max_length=120)
    tenant_name: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=120)
    agent: bool = False


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerifyBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)
    label: str | None = Field(default=None, max_length=120)
    tenant_id: str | None = None
    agent: bool = False


class TokenBody(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    kind: str = "user"
    agent: bool = False
    expires_days: int | None = Field(default=None, ge=1, le=730)
    project_id: str | None = Field(default=None, max_length=120)


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)


def _call(st: ServiceState, fn: Callable[[], Any], status: int = 200) -> JSONResponse:
    try:
        data = fn()
    except GraphError as e:
        env = {"ok": False, "error": e.to_dict(), "ontology_version": st.app.ontology_version}
        return respond(st, env)
    return respond(
        st, {"ok": True, "data": data, "ontology_version": st.app.ontology_version}, status
    )


def _send(st: ServiceState, to: str, message: tuple[str, str]) -> None:
    try:
        st.email.send(to, *message)
    except EmailError as e:
        log.error("email failed", extra={"error_code": "EMAIL"})
        raise GraphError(
            ErrorCode.FORBIDDEN, "Could not send the email", hint="Try again in a minute."
        ) from e


def _require_project(st: ServiceState, info: TokenInfo, project_id: str) -> None:
    """The project exists in the caller's tenant (other tenants' projects answer NOT_FOUND)."""
    env = st.app.call(info.principal, "get", node_id=project_id, depth=0)
    if not env.get("ok"):
        raise GraphError(ErrorCode.NOT_FOUND, f"Project {project_id!r} not found")
    node = env["data"]["node"]
    if node.get("parent_id") or node.get("class", "Project") != st.app.core.model.root_class:
        raise GraphError(ErrorCode.SCOPE_VIOLATION, f"{project_id!r} is not a project")


@router.post("/register")
def register(body: RegisterBody, st: ServiceState = Depends(state)) -> JSONResponse:
    return _call(
        st,
        lambda: st.identity.register(
            body.invite_code, body.email, body.name, body.tenant_name, body.label, body.agent
        ),
        201,
    )


@router.post("/login")
def login(body: LoginBody, st: ServiceState = Depends(state)) -> JSONResponse:
    def run() -> dict[str, Any]:
        code = st.identity.start_login(body.email)
        if code is not None:
            _send(st, body.email, login_email(code))
        # the same answer whether or not the address is registered
        return {"sent": True, "email": body.email}

    return _call(st, run, 202)


@router.post("/verify")
def verify(body: VerifyBody, st: ServiceState = Depends(state)) -> JSONResponse:
    return _call(
        st,
        lambda: st.identity.verify_login(
            body.email, body.code, body.label, body.tenant_id, body.agent
        ),
    )


@router.get("/me")
def me(info: TokenInfo = Depends(user_info), st: ServiceState = Depends(state)) -> JSONResponse:
    def run() -> dict[str, Any]:
        assert info.user_id is not None and info.tenant_id is not None
        user = st.identity.user(info.user_id) or {}
        return {
            "user": {k: user.get(k) for k in ("id", "email", "name", "created_at")},
            "tenant": st.identity.tenant(info.tenant_id),
            "tenants": st.identity.memberships(info.user_id),
            "token": {
                "id": info.token_id,
                "kind": info.kind,
                "expires_at": info.expires_at,
                "project_id": info.project_id,
            },
        }

    return _call(st, run)


@router.get("/tokens")
def tokens(info: TokenInfo = Depends(user_info), st: ServiceState = Depends(state)) -> JSONResponse:
    def run() -> dict[str, Any]:
        rows = st.identity.tokens(tenant_id=info.tenant_id)
        mine = [r for r in rows if r["user_id"] == info.user_id]
        return {"tokens": mine, "current": info.token_id}

    return _call(st, run)


@router.post("/tokens")
def create_token(
    body: TokenBody, info: TokenInfo = Depends(user_info), st: ServiceState = Depends(state)
) -> JSONResponse:
    def run() -> dict[str, Any]:
        assert info.user_id is not None and info.tenant_id is not None
        kwargs: dict[str, Any] = {"days": body.expires_days} if body.expires_days else {}
        if body.kind == "user":
            project_id = body.project_id or info.project_id  # a scoped token stays scoped
            if info.project_id and project_id != info.project_id:
                raise GraphError(
                    ErrorCode.FORBIDDEN,
                    "This token is limited to one project",
                    hint="Create tokens for other projects from an unrestricted login.",
                )
            if project_id:
                _require_project(st, info, project_id)
            return st.identity.issue_user_token(
                info.user_id,
                info.tenant_id,
                body.label,
                body.agent,
                project_id=project_id,
                **kwargs,
            )
        if body.kind == "ingest":
            if info.project_id:
                raise GraphError(
                    ErrorCode.FORBIDDEN, "A project-limited token cannot create ingest tokens"
                )
            return st.identity.issue_ingest_token(
                info.tenant_id, info.user_id, body.label, **kwargs
            )
        raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "kind must be user or ingest")

    return _call(st, run, 201)


@router.delete("/tokens/{token_id}")
def revoke_token(
    token_id: str, info: TokenInfo = Depends(user_info), st: ServiceState = Depends(state)
) -> JSONResponse:
    def run() -> dict[str, Any]:
        owned = {
            r["id"]
            for r in st.identity.tokens(tenant_id=info.tenant_id)
            if r["user_id"] == info.user_id
        }
        if token_id not in owned or not st.identity.revoke(token_id, info.tenant_id):
            raise GraphError(ErrorCode.NOT_FOUND, f"Active token {token_id!r} not found")
        return {"revoked": token_id}

    return _call(st, run)


@router.post("/invites")
def invite(
    body: InviteBody, info: TokenInfo = Depends(user_info), st: ServiceState = Depends(state)
) -> JSONResponse:
    """Invite a colleague into the caller's tenant (every member may invite; no RBAC yet)."""

    def run() -> dict[str, Any]:
        assert info.user_id is not None and info.tenant_id is not None
        if info.project_id:
            raise GraphError(
                ErrorCode.FORBIDDEN,
                "A project-limited token cannot invite people",
                hint="Invite from an unrestricted login (fwg login).",
            )
        row = st.identity.create_invite(body.email, info.user_id, info.tenant_id)
        tenant = st.identity.tenant(info.tenant_id) or {}
        _send(
            st,
            row["email"],
            invite_email(
                row["code"],
                st.settings.public_url,
                row["email"],
                tenant.get("name"),
                st.settings.cli_install,
            ),
        )
        return {k: v for k, v in row.items() if k != "code"}

    return _call(st, run, 201)
