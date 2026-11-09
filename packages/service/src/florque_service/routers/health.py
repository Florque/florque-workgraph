"""Probes and metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from florque_service.state import ServiceState, state

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@router.get("/readyz")
def readyz(st: ServiceState = Depends(state)) -> JSONResponse:
    # public endpoint: report readiness only, never store details (paths, sizes)
    try:
        ready = bool(st.app.core.store.health().get("ok"))
    except Exception:  # noqa: BLE001 - an unreachable store means not ready
        ready = False
    body = {"ok": ready, "ontology_version": st.app.ontology_version}
    return JSONResponse(body, status_code=200 if ready else 503)


@router.get("/metrics")
def metrics(st: ServiceState = Depends(state)) -> Response:
    return Response(generate_latest(st.metrics.registry), media_type=CONTENT_TYPE_LATEST)
