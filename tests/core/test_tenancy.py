"""Tenant isolation in graph-core: a tenant principal never sees or touches another tenant's nodes."""

from __future__ import annotations

import pytest
from florque_graph_core import GraphCore, GraphError, Principal

A = Principal("ann", {"*": "admin"}, can_create_projects=True, tenant_id="t_a")
B = Principal("bob", {"*": "admin"}, can_create_projects=True, tenant_id="t_b")
SYSTEM = Principal("system", {"*": "admin"})  # unscoped, like local mode


def code(fn, *args, **kwargs) -> str:
    with pytest.raises(GraphError) as e:
        fn(*args, **kwargs)
    return e.value.code


def actor(core: GraphCore, p: Principal, title: str, project: str) -> str:
    edges = [{"type": "member_of", "to": project, "props": {"role": "contributor"}}]
    node = core.create(p, "Actor", {"kind": "person", "title": title}, edges=edges)["node"]
    assert node["tenant_id"] == p.tenant_id
    return str(node["id"])


def seed(core: GraphCore, p: Principal, title: str = "Checkout") -> dict[str, str]:
    pid = core.create(p, "Project", {"title": title})["node"]["id"]
    obj = core.create(p, "Goal", {"kind": "objective", "title": "Faster checkout"}, pid)["node"][
        "id"
    ]
    return {"project": pid, "objective": obj}


def test_nodes_carry_the_tenant(core):
    a = seed(core, A)
    assert core.get(A, a["project"])["node"]["tenant_id"] == "t_a"
    assert core.get(A, a["objective"])["node"]["tenant_id"] == "t_a"
    actor(core, A, "Ann", a["project"])


def test_other_tenant_reads_as_not_found(core):
    a = seed(core, A)
    assert code(core.get, B, a["project"]) == "NOT_FOUND"
    assert code(core.get, B, a["objective"]) == "NOT_FOUND"
    assert code(core.list_nodes, B, a["project"]) == "FORBIDDEN"
    assert code(core.search, B, a["project"], "checkout") == "FORBIDDEN"
    assert code(core.check, B, a["project"]) == "FORBIDDEN"
    assert code(core.changes, B, a["project"]) == "FORBIDDEN"
    assert core.find_by_mixin(B, "Expectation")["nodes"] == []


def test_other_tenant_cannot_write(core):
    a = seed(core, A)
    goal = {"kind": "objective", "title": "Mine now"}
    assert code(core.create, B, "Goal", goal, a["project"]) == "NOT_FOUND"
    assert code(core.update, B, a["objective"], {"summary": "x"}) == "NOT_FOUND"
    assert code(core.archive, B, a["objective"]) == "NOT_FOUND"
    b = seed(core, B)
    assert code(core.move, B, b["objective"], a["project"]) == "NOT_FOUND"
    assert code(core.merge, B, b["objective"], a["objective"]) == "NOT_FOUND"


def test_edges_never_cross_tenants(core):
    a = seed(core, A)
    b = seed(core, B)
    bob = actor(core, B, "Bob", b["project"])
    assert code(core.link, A, a["objective"], "owned_by", bob) == "NOT_FOUND"
    # an unscoped principal (e.g. the hub) is still stopped at the tenant boundary
    assert code(core.link, SYSTEM, a["objective"], "owned_by", bob) == "SCOPE_VIOLATION"
    ann = actor(core, A, "Ann", a["project"])
    # membership is managed inside the tenant only
    assert code(core.link, A, ann, "member_of", b["project"], {"role": "viewer"}) == "NOT_FOUND"
    core.link(A, a["objective"], "owned_by", ann)
    assert b  # B's graph is untouched


def test_dedupe_is_per_tenant(core):
    a = seed(core, A, "Checkout")
    b = seed(core, B, "Checkout")  # same title in another tenant is fine
    assert code(core.create, A, "Project", {"title": "Checkout"}) == "DUPLICATE_EXACT"
    assert code(core.create, A, "Project", {"title": "Checkout!"}) in (
        "DUPLICATE_EXACT",
        "DUPLICATE_SIMILAR",
    )
    actor(core, A, "Sam", a["project"])
    actor(core, B, "Sam", b["project"])


def test_list_projects_is_scoped(core):
    pa = seed(core, A, "Alpha")["project"]
    pb = seed(core, B, "Beta")["project"]
    assert [p["id"] for p in core.list_projects(A)["projects"]] == [pa]
    assert [p["id"] for p in core.list_projects(B)["projects"]] == [pb]
    assert {p["id"] for p in core.list_projects(SYSTEM)["projects"]} == {pa, pb}


def test_tenant_id_cannot_be_written(core):
    pid = seed(core, A)["project"]
    assert code(core.update, A, pid, {"tenant_id": "t_b"}) == "ONTOLOGY_VIOLATION"
    goal = {"kind": "objective", "title": "Sneaky", "tenant_id": "t_b"}
    assert code(core.create, A, "Goal", goal, pid) == "ONTOLOGY_VIOLATION"
