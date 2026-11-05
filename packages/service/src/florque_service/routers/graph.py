"""Graph endpoints: ontology, nodes, edges, merge, recipes, integrity and audit (spec 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from florque_graph_core import Principal
from pydantic import BaseModel, Field

from florque_service.state import ServiceState, principal, respond, state

router = APIRouter(prefix="/v1")


class CreateBody(BaseModel):
    cls: str
    props: dict[str, Any] = Field(default_factory=dict)
    parent_id: str | None = None
    edges: list[dict[str, Any]] | None = None
    confirm_new: bool = False


class ProjectBody(BaseModel):
    cls: str = "Project"
    props: dict[str, Any] = Field(default_factory=dict)
    edges: list[dict[str, Any]] | None = None
    confirm_new: bool = False


class PatchBody(BaseModel):
    patch: dict[str, Any]
    if_version: int | None = None


class ArchiveBody(BaseModel):
    cascade: bool = False


class MoveBody(BaseModel):
    new_parent_id: str


class EdgeBody(BaseModel):
    src: str
    edge: str
    dst: str
    props: dict[str, Any] | None = None


class UnlinkBody(BaseModel):
    src: str
    edge: str
    dst: str


class MergeBody(BaseModel):
    keep: str
    drop: str


class CheckBody(BaseModel):
    project_id: str


class ListBody(BaseModel):
    project_id: str
    cls: str | None = None
    filters: dict[str, Any] | None = None
    include_archived: bool = False


@router.get("/ontology")
def ontology(st: ServiceState = Depends(state)) -> JSONResponse:
    # Public: version and card only, so clients can detect drift before authenticating.
    env = st.app.call(_anonymous(), "describe")
    return respond(st, env)


def _anonymous() -> Principal:
    return Principal(actor_id="anonymous", roles={})


@router.post("/projects")
def create_project(
    body: ProjectBody,
    idempotency_key: str | None = Header(default=None),
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    env = st.app.call(
        p,
        "create",
        cls="Project",
        props=body.props,
        edges=body.edges,
        idempotency_key=idempotency_key,
        confirm_new=body.confirm_new,
    )
    return respond(st, env, 201)


@router.post("/nodes")
def create_node(
    body: CreateBody,
    idempotency_key: str | None = Header(default=None),
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    env = st.app.call(
        p,
        "create",
        cls=body.cls,
        props=body.props,
        parent_id=body.parent_id,
        edges=body.edges,
        idempotency_key=idempotency_key,
        confirm_new=body.confirm_new,
    )
    return respond(st, env, 201)


@router.post("/nodes:list")
def list_nodes(
    body: ListBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "list_nodes", **body.model_dump()))


@router.get("/nodes/{node_id}")
def get_node(
    node_id: str,
    depth: int = 1,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "get", node_id=node_id, depth=depth))


@router.patch("/nodes/{node_id}")
def update_node(
    node_id: str,
    body: PatchBody,
    idempotency_key: str | None = Header(default=None),
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    env = st.app.call(
        p,
        "update",
        node_id=node_id,
        patch=body.patch,
        if_version=body.if_version,
        idempotency_key=idempotency_key,
    )
    return respond(st, env)


@router.post("/nodes/{node_id}:archive")
def archive_node(
    node_id: str,
    body: ArchiveBody | None = None,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(
        st, st.app.call(p, "archive", node_id=node_id, cascade=bool(body and body.cascade))
    )


@router.post("/nodes/{node_id}:move")
def move_node(
    node_id: str,
    body: MoveBody,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "move", node_id=node_id, new_parent_id=body.new_parent_id))


@router.get("/search")
def search(
    project_id: str,
    q: str,
    cls: str | None = None,
    limit: int = 20,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(
        st, st.app.call(p, "search", project_id=project_id, query=q, cls=cls, limit=limit)
    )


@router.post("/edges")
def link(
    body: EdgeBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "link", **body.model_dump()), 201)


@router.post("/edges:unlink")
def unlink(
    body: UnlinkBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "unlink", **body.model_dump()))


@router.post("/merge")
def merge(
    body: MergeBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "merge", keep=body.keep, drop=body.drop))


@router.get("/recipes")
def recipes(p: Principal = Depends(principal), st: ServiceState = Depends(state)) -> JSONResponse:
    return respond(st, st.app.call(p, "recipes"))


@router.get("/recipes/{name}")
def recipe(
    name: str,
    request: Request,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "recipe", name=name, args=dict(request.query_params)))


@router.post("/check")
def check(
    body: CheckBody, p: Principal = Depends(principal), st: ServiceState = Depends(state)
) -> JSONResponse:
    return respond(st, st.app.call(p, "check", project_id=body.project_id))


@router.get("/changes")
def changes(
    project_id: str,
    since: str | None = None,
    limit: int = 100,
    p: Principal = Depends(principal),
    st: ServiceState = Depends(state),
) -> JSONResponse:
    return respond(st, st.app.call(p, "changes", project_id=project_id, since=since, limit=limit))
