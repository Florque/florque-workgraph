"""Hub endpoints: push ingestion, registry (admin) and inbox triage (spec 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from florque_graph_core import Principal
from pydantic import BaseModel, Field

from florque_service.state import ServiceState, ingest_principal, principal, respond, state

router = APIRouter(prefix="/v1/hub")


class SourceBody(BaseModel):
    id: str
    kind: str
    name: str | None = None
    config: dict[str, Any] | None = None


class SensorBody(BaseModel):
    series_code: str
    project_id: str
    unit: str
    aggregation: str = "last"
    source_id: str | None = None
    description: str | None = None


class BindingBody(BaseModel):
    kind: str
    binding: dict[str, Any] = Field(default_factory=dict)


class ResolveBody(BaseModel):
    action: str
    node_id: str | None = None


class EvaluateBody(BaseModel):
    node_id: str | None = None
    project_id: str | None = None


@router.post("/observations")
def ingest(
    observation: dict[str, Any] = Body(...),
    p: Principal = Depends(ingest_principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_ingest", observation=observation), 202)


@router.get("/sources")
def sources(p: Principal = Depends(principal), st: ServiceState = Depends(state)) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_sources"))


@router.post("/sources")
def add_source(
    body: SourceBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_source_add", **body.model_dump()), 201)


@router.delete("/sources/{source_id}")
def archive_source(
    source_id: str, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_source_archive", id=source_id))


@router.get("/sensors")
def sensors(
    project_id: str | None = None,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_sensors", project_id=project_id))


@router.post("/sensors")
def add_sensor(
    body: SensorBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_sensor_add", **body.model_dump()), 201)


@router.delete("/sensors/{sensor_id}")
def archive_sensor(
    sensor_id: str, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_sensor_archive", id=sensor_id))


@router.get("/bindings")
def bindings(
    kind: str = "channel", p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_bindings", kind=kind))


@router.post("/bindings")
def add_binding(
    body: BindingBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_binding_add", kind=body.kind, binding=body.binding), 201)


@router.delete("/bindings/{kind}/{binding_id}")
def archive_binding(
    kind: str, binding_id: str, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_binding_archive", kind=kind, id=binding_id))


@router.get("/inbox")
def inbox(
    status: str | None = "open",
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_inbox", status=status))


@router.post("/inbox/{item_id}:resolve")
def resolve(
    item_id: str,
    body: ResolveBody,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(
        st,
        st.app.call(p, "hub_inbox_resolve", id=item_id, action=body.action, node_id=body.node_id),
    )


@router.post("/evaluate")
def evaluate(
    body: EvaluateBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(
        st, st.app.call(p, "hub_evaluate", node_id=body.node_id, project_id=body.project_id)
    )


@router.post("/reconcile")
def reconcile(p: Principal = Depends(principal), st: ServiceState = Depends(state)) -> JSONResponse:
    return respond(st, st.app.call(p, "hub_reconcile"))
