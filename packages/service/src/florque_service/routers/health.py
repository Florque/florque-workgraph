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
    db = st.app.core.store.health()
    ready = bool(db.get("ok"))
    body = {
        "ok": ready,
        "database": db,
        "ontology_version": st.app.ontology_version,
        "mixins_version": st.app.hub.contract.mixins_version,
    }
    return JSONResponse(body, status_code=200 if ready else 503)


@router.get("/metrics")
def metrics(st: ServiceState = Depends(state)) -> Response:
    return Response(generate_latest(st.metrics.registry), media_type=CONTENT_TYPE_LATEST)
