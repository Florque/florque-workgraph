"""Per-process service state and FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from florque_client.app import FlorqueApp
from florque_graph_core import Principal

from florque_service.auth import TokenStore
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
    "SCOPE_VIOLATION": 422,
    "ONTOLOGY_VIOLATION": 422,
    "PARENT_RULE": 422,
    "REQUIRED_EDGE": 422,
}


@dataclass
class ServiceState:
    app: FlorqueApp
    tokens: TokenStore
    metrics: Metrics


def state(request: Request) -> ServiceState:
    return request.app.state.florque  # type: ignore[no-any-return]


class AuthError(Exception):
    pass


def principal(
    authorization: str | None = Header(default=None),
    st: ServiceState = Depends(state),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    p = st.tokens.principal(authorization.split(" ", 1)[1].strip())
    if p is None:
        raise AuthError("invalid or revoked token")
    return p


def respond(st: ServiceState, env: dict[str, Any], ok_status: int = 200) -> JSONResponse:
    if env.get("ok"):
        return JSONResponse(env, status_code=ok_status)
    code = env["error"]["code"]
    st.metrics.failures.labels(code).inc()
    return JSONResponse(env, status_code=STATUS.get(code, 400))
