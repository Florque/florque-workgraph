"""Per-tenant and per-project ontology extensions through FlorqueApp."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from florque_client import FlorqueApp, build_app
from florque_graph_core import Principal

from tests.core.test_extensions import EXPERIMENTS

A = Principal("ann", {"*": "admin"}, can_create_projects=True, tenant_id="t_a")
B = Principal("bob", {"*": "admin"}, can_create_projects=True, tenant_id="t_b")

BILLING = """
name: billing
version: 0.1.0
slots:
  invoice_ref:
    range: string
classes:
  Invoice:
    is_a: Node
    slots: [invoice_ref]
    annotations:
      allowed_parent: Project
"""


@pytest.fixture
def app() -> Iterator[FlorqueApp]:
    a = build_app()
    yield a
    a.close()


def ok(env):
    assert env["ok"], env.get("error")
    return env


def err(env):
    assert not env["ok"], env
    return env["error"]


def project(app: FlorqueApp, p: Principal, title: str = "Checkout") -> str:
    return ok(app.call(p, "create", cls="Project", props={"title": title}))["data"]["node"]["id"]


def initiative(app: FlorqueApp, p: Principal, pid: str) -> str:
    obj = ok(
        app.call(p, "create", cls="Goal", props={"kind": "objective", "title": "O"}, parent_id=pid)
    )["data"]["node"]["id"]
    return ok(
        app.call(
            p,
            "create",
            cls="WorkItem",
            props={"kind": "initiative", "title": "I"},
            parent_id=pid,
            edges=[{"type": "serves", "to": obj}],
        )
    )["data"]["node"]["id"]


def test_tenant_extension_applies_to_its_projects_only(app):
    pa, pb = project(app, A), project(app, B)
    ia, ib = initiative(app, A, pa), initiative(app, B, pb)
    out = ok(app.call(A, "ontology_add", yaml=EXPERIMENTS))["data"]
    assert out["ontology_version"] == "0.2.0+experiments@1.0.0"
    assert out["classes_added"] == ["Experiment"]
    assert out["kinds_added"] == {"WorkItem": ["spike"]}

    exp = {"kind": "ab_test", "title": "Price test", "hypothesis": "cheaper sells"}
    env = ok(app.call(A, "create", cls="Experiment", props=exp, parent_id=ia))
    assert env["ontology_version"] == "0.2.0+experiments@1.0.0"
    assert env["data"]["node"]["tenant_id"] == "t_a"
    spike = {"kind": "spike", "title": "Look into it"}
    ok(app.call(A, "create", cls="WorkItem", props=spike, parent_id=ia))

    # tenant B still has the base ontology
    assert err(app.call(B, "create", cls="Experiment", props=exp, parent_id=ib))["code"] == (
        "ONTOLOGY_VIOLATION"
    )
    assert app.call(B, "describe", project_id=pb)["data"]["ontology_version"] == "0.2.0"
    described = ok(app.call(A, "describe", project_id=pa))["data"]
    assert "Experiment" in described["classes"] and "Experiment" in described["card"]
    assert [e["name"] for e in ok(app.call(A, "ontology_extensions"))["data"]["extensions"]] == [
        "experiments"
    ]
    assert ok(app.call(B, "ontology_extensions"))["data"]["extensions"] == []


def test_project_extension_and_resolution_order(app):
    p1, p2 = project(app, A, "One"), project(app, A, "Two")
    ok(app.call(A, "ontology_add", yaml=EXPERIMENTS))
    ok(app.call(A, "ontology_add", yaml=BILLING, project_id=p1))
    v1 = ok(app.call(A, "describe", project_id=p1))["data"]["ontology_version"]
    v2 = ok(app.call(A, "describe", project_id=p2))["data"]["ontology_version"]
    assert v1 == "0.2.0+experiments@1.0.0+billing@0.1.0"
    assert v2 == "0.2.0+experiments@1.0.0"
    inv = {"title": "Nov invoice", "invoice_ref": "INV-1"}
    ok(app.call(A, "create", cls="Invoice", props=inv, parent_id=p1))
    assert err(app.call(A, "create", cls="Invoice", props=inv, parent_id=p2))["code"] == (
        "ONTOLOGY_VIOLATION"
    )


def test_versions_and_dry_run(app):
    pa = project(app, A)
    ia = initiative(app, A, pa)
    ok(app.call(A, "ontology_add", yaml=EXPERIMENTS))
    assert err(app.call(A, "ontology_add", yaml=EXPERIMENTS))["code"] == "DUPLICATE_EXACT"
    exp = {"kind": "ab_test", "title": "Price test", "hypothesis": "h"}
    ok(app.call(A, "create", cls="Experiment", props=exp, parent_id=ia))

    # a new version that drops the class in use is refused
    v2 = "name: experiments\nversion: 2.0.0\n"
    e = err(app.call(A, "ontology_add", yaml=v2))
    assert e["code"] == "ONTOLOGY_VIOLATION" and e["details"]["problems"]
    # so is retiring it
    ext_id = ok(app.call(A, "ontology_extensions"))["data"]["extensions"][0]["id"]
    assert err(app.call(A, "ontology_retire", id=ext_id))["code"] == "ONTOLOGY_VIOLATION"
    # other tenants cannot see or retire it
    assert err(app.call(B, "ontology_retire", id=ext_id))["code"] == "NOT_FOUND"


def test_validate_does_not_store(app):
    project(app, A)
    out = ok(app.call(A, "ontology_validate", yaml=EXPERIMENTS))["data"]
    assert out["ontology_version"] == "0.2.0+experiments@1.0.0"
    assert ok(app.call(A, "ontology_extensions"))["data"]["extensions"] == []


def test_extension_cannot_break_the_hub_contract(app):
    project(app, A)
    second_expectation = """
name: kpis
version: 1.0.0
classes:
  Kpi:
    is_a: Node
    mixins: [Expectation]
    annotations:
      allowed_parent: Project
"""
    e = err(app.call(A, "ontology_add", yaml=second_expectation))
    assert e["code"] == "ONTOLOGY_VIOLATION" and "hub contract" in e["message"]


def test_hub_keeps_working_on_extended_projects(app):
    from tests.conftest import KR_PROPS

    pa = project(app, A)
    ok(app.call(A, "ontology_add", yaml=EXPERIMENTS))
    obj = ok(
        app.call(A, "create", cls="Goal", props={"kind": "objective", "title": "O"}, parent_id=pa)
    )["data"]["node"]["id"]
    ok(app.call(A, "hub_source_add", id="metrics", kind="sensor"))
    ok(app.call(A, "hub_sensor_add", series_code="dau", project_id=pa, unit="users"))
    kr = ok(app.call(A, "create", cls="Goal", props=KR_PROPS, parent_id=obj))["data"]["node"]["id"]
    ingest = Principal("ingest", {"*": "hub"}, is_agent=True, tenant_id="t_a")
    out = ok(
        app.call(
            ingest,
            "hub_ingest",
            observation={
                "source_id": "metrics",
                "external_id": "m1",
                "subject_code": "dau",
                "type": "metric",
                "value": 1200,
                "observed_at": "2026-11-09T10:00:00Z",
            },
        )
    )["data"]
    assert out["evaluations"][0]["node_id"] == kr
    assert ok(app.call(A, "get", node_id=kr))["data"]["node"]["last_value"] == 1200
