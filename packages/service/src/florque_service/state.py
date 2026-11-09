"""Per-process service state and FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from florque_client.app import FlorqueApp
from florque_graph_core import Principal

from florque_service.email import ConsoleSender, EmailSender
from florque_service.identity import IdentityStore, TokenInfo
from florque_service.observability import Metrics

STATUS = {
    "NOT_FOUND": 404,
    "VERSION_CONFLICT": 409,
    "DUPLICATE_EXACT": 409,
    "DUPLICATE_SIMILAR": 409,
    "MERGE_CONFLICT": 409,
    "FORBIDDEN": 403,
    "OWNERSHIP": 403,
    "UNAUTHENTICATED": 401,
    "RATE_LIMITED": 429,
    "SCOPE_VIOLATION": 422,
    "ONTOLOGY_VIOLATION": 422,
    "PARENT_RULE": 422,
    "REQUIRED_EDGE": 422,
}


@dataclass
class Settings:
    public_url: str = "http://127.0.0.1:8000"
    cli_install: str = "uv tool install florque-cli"
    min_client: str = "0.2.0"


@dataclass
class ServiceState:
    app: FlorqueApp
    identity: IdentityStore
    metrics: Metrics
    email: EmailSender = field(default_factory=ConsoleSender)
    settings: Settings = field(default_factory=Settings)

    @property
    def tokens(self) -> IdentityStore:  # backwards-compatible name
        return self.identity


def state(request: Request) -> ServiceState:
    return request.app.state.florque  # type: ignore[no-any-return]


class AuthError(Exception):
    """No valid credentials: 401."""


class TokenKindError(Exception):
    """Valid credentials of a kind this endpoint does not accept: 403."""


def token_info(
    authorization: str | None = Header(default=None),
    st: ServiceState = Depends(state),
) -> TokenInfo:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    info = st.identity.resolve(authorization.split(" ", 1)[1].strip())
    if info is None:
        raise AuthError("invalid, expired or revoked token")
    return info


def principal(info: TokenInfo = Depends(token_info)) -> Principal:
    """Any user or operator token. Ingest tokens may only push observations."""
    if info.kind == "ingest":
        raise TokenKindError("ingest tokens may only call POST /v1/hub/observations")
    return info.principal


def optional_principal(
    authorization: str | None = Header(default=None),
    st: ServiceState = Depends(state),
) -> Principal | None:
    """The caller when credentials are sent (invalid ones still fail), else None."""
    if not authorization:
        return None
    return principal(token_info(authorization, st))


def ingest_principal(info: TokenInfo = Depends(token_info)) -> Principal:
    return info.principal


def user_info(info: TokenInfo = Depends(token_info)) -> TokenInfo:
    if info.kind != "user":
        raise TokenKindError("this endpoint needs a user token (fwg login)")
    return info


def respond(st: ServiceState, env: dict[str, Any], ok_status: int = 200) -> JSONResponse:
    if env.get("ok"):
        return JSONResponse(env, status_code=ok_status)
    code = env["error"]["code"]
    st.metrics.failures.labels(code).inc()
    return JSONResponse(env, status_code=STATUS.get(code, 400))
