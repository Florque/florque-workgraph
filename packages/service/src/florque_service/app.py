"""florque-service: HTTP API under /v1, auth, workers (spec 7)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from florque_client.app import FlorqueApp, build_app
from florque_client.config import load_config

from florque_service.email import ConsoleSender, EmailSender, invite_email, sender_from_env
from florque_service.identity import IdentityStore
from florque_service.observability import Metrics, configure_logging, request_middleware
from florque_service.ratelimit import RateLimiter
from florque_service.routers import auth, graph, health, hub
from florque_service.state import AuthError, ServiceState, Settings, TokenKindError

MAX_BODY_BYTES = 1024 * 1024


def _service_db(hub_db: str) -> str:
    return os.environ.get("FLORQUE_SERVICE_DB") or (
        ":memory:" if hub_db == ":memory:" else str(Path(hub_db).with_name("service.sqlite"))
    )


def settings_from_env() -> Settings:
    return Settings(
        public_url=os.environ.get("FLORQUE_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
        cli_install=os.environ.get("FLORQUE_CLI_INSTALL", "uv tool install florque-cli"),
        min_client=os.environ.get("FLORQUE_MIN_CLIENT", "0.2.0"),
    )


def _envelope(code: str, message: str, hint: str, version: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "hint": hint, "details": {}},
        "ontology_version": version,
    }


def _token_key(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    parts = auth_header.split(" ", 1)[-1].split("_", 2)
    if len(parts) == 3 and parts[0] == "fwg":
        return f"tok:{parts[1]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def create_app(
    app: FlorqueApp | None = None,
    identity: IdentityStore | None = None,
    *,
    scheduler: bool | None = None,
    email: EmailSender | None = None,
    settings: Settings | None = None,
    rate_limit: int | None = None,
    auth_rate_limit: int | None = None,
) -> FastAPI:
    if app is None:
        cfg = load_config()
        app = build_app(cfg)
        identity = identity or IdentityStore(_service_db(cfg.hub_db))
        email = email or sender_from_env()
        settings = settings or settings_from_env()
    identity = identity or IdentityStore()
    email = email or ConsoleSender()
    settings = settings or Settings()
    run_scheduler = (
        scheduler if scheduler is not None else os.environ.get("FLORQUE_SCHEDULER", "on") != "off"
    )
    general = RateLimiter(
        rate_limit if rate_limit is not None else int(os.environ.get("FLORQUE_RATE_LIMIT", "600"))
    )
    strict = RateLimiter(
        auth_rate_limit
        if auth_rate_limit is not None
        else int(os.environ.get("FLORQUE_AUTH_RATE_LIMIT", "20"))
    )
    metrics = Metrics()
    florque = app

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        sched = None
        if run_scheduler:
            from florque_service.scheduler import start_scheduler

            sched = start_scheduler(florque)
        yield
        if sched is not None:
            sched.shutdown(wait=False)

    api = FastAPI(
        title="Florque Workgraph API",
        version=app.ontology_version,
        description="Typed project graph with validated writes. Every response carries ontology_version.",
        lifespan=lifespan,
    )
    api.state.florque = ServiceState(
        app=app, identity=identity, metrics=metrics, email=email, settings=settings
    )

    @api.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith("/v1/"):
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
                return JSONResponse(
                    _envelope(
                        "ONTOLOGY_VIOLATION", "Request body too large", "", florque.ontology_version
                    ),
                    status_code=413,
                )
            if path.startswith("/v1/auth/") and request.method == "POST":
                ip = request.client.host if request.client else "unknown"
                allowed, wait = strict.allow(f"auth:{ip}")
            else:
                allowed, wait = general.allow(_token_key(request))
            if not allowed:
                metrics.failures.labels("RATE_LIMITED").inc()
                return JSONResponse(
                    _envelope(
                        "RATE_LIMITED",
                        "Too many requests",
                        f"Retry in {int(wait) + 1} s.",
                        florque.ontology_version,
                    ),
                    status_code=429,
                    headers={"Retry-After": str(int(wait) + 1)},
                )
        response = await call_next(request)
        response.headers["X-Florque-Min-Client"] = settings.min_client
        return response

    api.middleware("http")(request_middleware(metrics))

    @api.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError) -> JSONResponse:
        metrics.failures.labels("UNAUTHENTICATED").inc()
        return JSONResponse(
            _envelope(
                "UNAUTHENTICATED",
                str(exc),
                "Run fwg login, or set FLORQUE_TOKEN.",
                florque.ontology_version,
            ),
            status_code=401,
        )

    @api.exception_handler(TokenKindError)
    async def _kind(_: Request, exc: TokenKindError) -> JSONResponse:
        metrics.failures.labels("FORBIDDEN").inc()
        return JSONResponse(
            _envelope(
                "FORBIDDEN", str(exc), "Use a user token for this call.", florque.ontology_version
            ),
            status_code=403,
        )

    @api.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        metrics.failures.labels("ONTOLOGY_VIOLATION").inc()
        env = _envelope(
            "ONTOLOGY_VIOLATION",
            "Malformed request",
            "Check the request body against the OpenAPI schema at /docs.",
            florque.ontology_version,
        )
        env["error"]["details"] = {"errors": json.loads(json.dumps(exc.errors(), default=str))}
        return JSONResponse(env, status_code=422)

    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(graph.router)
    api.include_router(hub.router)
    return api


# ---------------------------------------------------------------- operator CLI


def _parse_roles(values: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for v in values:
        project, sep, role = v.partition("=")
        if not sep:
            raise SystemExit(f"--role expects PROJECT=ROLE (or *=ROLE), got {v!r}")
        roles[project] = role
    return roles


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> Any:
    ap = argparse.ArgumentParser(prog="florque-service")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    inv = sub.add_parser("invite", help="invite people (operator command)")
    isub = inv.add_subparsers(dest="icmd", required=True)
    icreate = isub.add_parser("create", help="create an invite and email it")
    icreate.add_argument("--email", required=True)
    icreate.add_argument("--tenant-id", help="join an existing tenant instead of creating one")
    icreate.add_argument("--no-email", action="store_true", help="only print the code")
    isub.add_parser("list")

    ten = sub.add_parser("tenant", help="tenants (operator command)")
    ten.add_subparsers(dest="tcmd", required=True).add_parser("list")
    usr = sub.add_parser("user", help="users (operator command)")
    usr.add_subparsers(dest="ucmd", required=True).add_parser("list")

    tok = sub.add_parser("token", help="operator tokens: issue, list or revoke")
    tsub = tok.add_subparsers(dest="tcmd", required=True)
    issue = tsub.add_parser("issue", help="an operator token with an explicit role map")
    issue.add_argument("--actor", required=True)
    issue.add_argument(
        "--role", action="append", default=[], help="PROJECT=ROLE or *=ROLE; repeatable"
    )
    issue.add_argument("--create-projects", action="store_true")
    issue.add_argument("--agent", action="store_true")
    issue.add_argument("--label")
    issue.add_argument("--days", type=float, help="expiry in days (default: none)")
    revoke = tsub.add_parser("revoke")
    revoke.add_argument("token_id")
    tsub.add_parser("list")
    args = ap.parse_args(argv)

    configure_logging(os.environ.get("FLORQUE_LOG_LEVEL", "INFO").upper())
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run(
            create_app(),
            host=args.host,
            port=args.port,
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips=os.environ.get("FLORQUE_FORWARDED_ALLOW_IPS", "127.0.0.1"),
        )
        return 0
    cfg = load_config()
    store = IdentityStore(_service_db(cfg.hub_db))
    if args.cmd == "invite":
        if args.icmd == "list":
            _print(store.invites())
            return 0
        row = store.create_invite(args.email, "operator", args.tenant_id)
        if not args.no_email:
            settings = settings_from_env()
            tenant = store.tenant(args.tenant_id) if args.tenant_id else None
            sender_from_env().send(
                row["email"],
                *invite_email(
                    row["code"],
                    settings.public_url,
                    row["email"],
                    tenant["name"] if tenant else None,
                    settings.cli_install,
                ),
            )
        _print(row)
        return 0
    if args.cmd == "tenant":
        _print(store.tenants())
        return 0
    if args.cmd == "user":
        _print(store.users())
        return 0
    if args.tcmd == "issue":
        out = store.issue(
            args.actor,
            _parse_roles(args.role),
            args.create_projects,
            args.agent,
            args.label,
            args.days,
        )
        _print(out)
        print("Store the token in FLORQUE_TOKEN; it is not shown again.", file=sys.stderr)
    elif args.tcmd == "revoke":
        _print({"revoked": store.revoke(args.token_id)})
    else:
        _print(store.list())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
