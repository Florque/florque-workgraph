"""florque-service: HTTP API under /v1, auth, workers (spec 7)."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from florque_client.app import FlorqueApp, build_app
from florque_client.config import load_config

from florque_service.auth import TokenStore
from florque_service.observability import Metrics, configure_logging, request_middleware
from florque_service.routers import graph, health, hub
from florque_service.state import AuthError, ServiceState


def _service_db(hub_db: str) -> str:
    return os.environ.get("FLORQUE_SERVICE_DB") or (
        ":memory:" if hub_db == ":memory:" else str(Path(hub_db).with_name("service.sqlite"))
    )


def create_app(
    app: FlorqueApp | None = None,
    tokens: TokenStore | None = None,
    *,
    scheduler: bool | None = None,
) -> FastAPI:
    if app is None:
        cfg = load_config()
        app = build_app(cfg)
        tokens = tokens or TokenStore(_service_db(cfg.hub_db))
    tokens = tokens or TokenStore()
    run_scheduler = (
        scheduler if scheduler is not None else os.environ.get("FLORQUE_SCHEDULER", "on") != "off"
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
    api.state.florque = ServiceState(app=app, tokens=tokens, metrics=metrics)
    api.middleware("http")(request_middleware(metrics))

    @api.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError) -> JSONResponse:
        metrics.failures.labels("UNAUTHENTICATED").inc()
        return JSONResponse(
            {
                "ok": False,
                "error": {
                    "code": "UNAUTHENTICATED",
                    "message": str(exc),
                    "hint": "Set FLORQUE_TOKEN.",
                    "details": {},
                },
                "ontology_version": florque.ontology_version,
            },
            status_code=401,
        )

    @api.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        metrics.failures.labels("ONTOLOGY_VIOLATION").inc()
        return JSONResponse(
            {
                "ok": False,
                "error": {
                    "code": "ONTOLOGY_VIOLATION",
                    "message": "Malformed request",
                    "hint": "Check the request body against the OpenAPI schema at /docs.",
                    "details": {"errors": json.loads(json.dumps(exc.errors(), default=str))},
                },
                "ontology_version": florque.ontology_version,
            },
            status_code=422,
        )

    api.include_router(health.router)
    api.include_router(graph.router)
    api.include_router(hub.router)
    return api


def _parse_roles(values: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for v in values:
        project, sep, role = v.partition("=")
        if not sep:
            raise SystemExit(f"--role expects PROJECT=ROLE (or *=ROLE), got {v!r}")
        roles[project] = role
    return roles


def main(argv: list[str] | None = None) -> Any:
    ap = argparse.ArgumentParser(prog="florque-service")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    tok = sub.add_parser("token", help="issue, list or revoke API tokens (admin command)")
    tsub = tok.add_subparsers(dest="tcmd", required=True)
    issue = tsub.add_parser("issue")
    issue.add_argument("--actor", required=True)
    issue.add_argument(
        "--role", action="append", default=[], help="PROJECT=ROLE or *=ROLE; repeatable"
    )
    issue.add_argument("--create-projects", action="store_true")
    issue.add_argument("--agent", action="store_true")
    issue.add_argument("--label")
    revoke = tsub.add_parser("revoke")
    revoke.add_argument("token_id")
    tsub.add_parser("list")
    args = ap.parse_args(argv)

    configure_logging()
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run(create_app(), host=args.host, port=args.port, log_config=None)
        return 0
    cfg = load_config()
    store = TokenStore(_service_db(cfg.hub_db))
    if args.tcmd == "issue":
        out = store.issue(
            args.actor, _parse_roles(args.role), args.create_projects, args.agent, args.label
        )
        print(json.dumps(out, indent=2))
        print(
            "Store the token in FLORQUE_TOKEN; it is not shown again.",
            file=__import__("sys").stderr,
        )
    elif args.tcmd == "revoke":
        print(json.dumps({"revoked": store.revoke(args.token_id)}))
    else:
        print(json.dumps(store.list(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
