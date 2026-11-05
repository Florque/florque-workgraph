"""Structured JSON logs and Prometheus metrics (spec 7, Operations)."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from fastapi import Request, Response
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key in (
            "method",
            "path",
            "status",
            "duration_ms",
            "idempotency_key",
            "error_code",
            "actor_id",
        ):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("florque")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.latency = Histogram(
            "florque_request_seconds",
            "Request latency",
            ["method", "route"],
            registry=self.registry,
        )
        self.failures = Counter(
            "florque_validation_failures_total",
            "Rejected requests by error code",
            ["code"],
            registry=self.registry,
        )
        self.hub_lag = Gauge(
            "florque_hub_lag_seconds", "Age of the oldest queued hub job", registry=self.registry
        )
        self.expectations = Gauge(
            "florque_expectations", "Expectations by outcome", ["outcome"], registry=self.registry
        )


log = logging.getLogger("florque.service")


def request_middleware(
    metrics: Metrics,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def mw(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            dur = time.perf_counter() - start
            route = request.scope.get("route")
            metrics.latency.labels(request.method, getattr(route, "path", "unmatched")).observe(dur)
            response.headers["X-Request-ID"] = rid
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(dur * 1000, 1),
                    "idempotency_key": request.headers.get("Idempotency-Key"),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    return mw
