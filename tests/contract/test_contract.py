"""One contract suite against both the in-process and the HTTP client (spec 11)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from florque_client import Client, HttpClient, LocalClient, build_app
from florque_graph_core.store.memory import MemoryStore
from florque_service import TokenStore, create_app
from florque_signal_hub import SQLiteHubStore

from tests.conftest import ADMIN, KR_PROPS, Clock


@pytest.fixture(params=["local", "http"])
def client(request: pytest.FixtureRequest, clock: Clock) -> Iterator[Client]:
    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore(), clock=clock)
    if request.param == "local":
        yield LocalClient(app, ADMIN)
        return
    tokens = TokenStore()
    token = tokens.issue("alice", {"*": "admin"}, can_create_projects=True)["token"]
    with TestClient(create_app(app, tokens, scheduler=False)) as tc:
        yield HttpClient(http=tc, token=token)


def ok(env):
    assert env["ok"], env.get("error")
    assert env["ontology_version"] == "0.2.0"
    return env["data"]


def err(env):
    assert not env["ok"]
    assert env["ontology_version"] == "0.2.0"
    assert set(env["error"]) == {"code", "message", "hint", "details"}
    return env["error"]["code"]


def start_project(c: Client) -> dict[str, str]:
    pid = ok(c.create("Project", {"title": "Checkout"}))["node"]["id"]
    obj = ok(c.create("Goal", {"kind": "objective", "title": "Faster checkout"}, pid))["node"]["id"]
    ok(c.hub_source_add("metrics", "sensor"))
    ok(c.hub_sensor_add("dau", pid, "users", source_id="metrics"))
    kr = ok(c.create("Goal", KR_PROPS, obj))["node"]["id"]
    ini = ok(
        c.create(
            "WorkItem",
            {"kind": "initiative", "title": "Payment rewrite"},
            pid,
            [{"type": "serves", "to": kr}],
        )
    )["node"]["id"]
    task = ok(c.create("WorkItem", {"kind": "task", "title": "Tokenize cards"}, ini))["node"]["id"]
    return {"project": pid, "objective": obj, "kr": kr, "initiative": ini, "task": task}


def test_describe(client):
    d = ok(client.describe())
    assert "Goal" in d["classes"] and d["mixins_version"] == "0.1.0"


def test_start_project_has_no_orphans(client):
    ids = start_project(client)
    assert ok(client.check(ids["project"])) == {"ok": True, "violations": []}
    overview = ok(client.recipe("project_overview", {"project_id": ids["project"]}))
    assert overview["objectives"][0]["key_results"][0]["id"] == ids["kr"]


def test_errors_are_identical(client):
    ids = start_project(client)
    assert (
        err(client.create("WorkItem", {"kind": "task", "title": "x"}, ids["project"]))
        == "PARENT_RULE"
    )
    assert (
        err(client.create("WorkItem", {"kind": "initiative", "title": "x"}, ids["project"]))
        == "REQUIRED_EDGE"
    )
    assert (
        err(
            client.create(
                "WorkItem", {"kind": "task", "title": "Tokenize cards"}, ids["initiative"]
            )
        )
        == "DUPLICATE_EXACT"
    )
    assert (
        err(
            client.create(
                "WorkItem", {"kind": "task", "title": "Tokenise cards"}, ids["initiative"]
            )
        )
        == "DUPLICATE_SIMILAR"
    )
    assert err(client.update(ids["kr"], {"outcome": "succeeded"})) == "OWNERSHIP"
    assert err(client.update(ids["task"], {"summary": "x"}, if_version=99)) == "VERSION_CONFLICT"
    assert err(client.get("missing")) == "NOT_FOUND"
    assert err(client.unlink(ids["initiative"], "serves", ids["kr"])) == "REQUIRED_EDGE"


def test_idempotency(client):
    ids = start_project(client)
    a = ok(
        client.create(
            "WorkItem", {"kind": "task", "title": "Docs"}, ids["initiative"], idempotency_key="abc"
        )
    )
    b = ok(
        client.create(
            "WorkItem", {"kind": "task", "title": "Docs"}, ids["initiative"], idempotency_key="abc"
        )
    )
    assert a["node"]["id"] == b["node"]["id"]


def test_lifecycle(client):
    ids = start_project(client)
    epic = ok(client.create("WorkItem", {"kind": "epic", "title": "Cards"}, ids["initiative"]))[
        "node"
    ]["id"]
    ok(client.move(ids["task"], epic))
    ok(client.link(ids["task"], "depends_on", epic))
    ok(client.unlink(ids["task"], "depends_on", epic))
    assert ok(client.update(ids["task"], {"summary": "PCI scope"}))["node"]["version"] == 3
    assert ok(client.archive(epic, cascade=True))["archived"] == [epic, ids["task"]]
    assert [c["op"] for c in ok(client.changes(ids["project"]))["changes"]][-1] == "archive"
    assert (
        ok(client.search(ids["project"], "payment"))["results"][0]["node"]["id"]
        == ids["initiative"]
    )


def test_hub_flow(client, clock):
    ids = start_project(client)
    now = clock.now
    for i, v in enumerate([500, 900, 1300]):
        out = ok(
            client.hub_ingest(
                {
                    "source_id": "metrics",
                    "external_id": f"x{i}",
                    "subject_code": "dau",
                    "type": "metric",
                    "value": v,
                    "observed_at": (now - timedelta(days=2 - i)).isoformat(),
                }
            )
        )
        assert out["status"] == "accepted"
    assert (
        ok(
            client.hub_ingest(
                {
                    "source_id": "metrics",
                    "external_id": "x0",
                    "subject_code": "dau",
                    "type": "metric",
                    "value": 500,
                    "observed_at": now.isoformat(),
                }
            )
        )["status"]
        == "duplicate"
    )
    clock.now = now + timedelta(days=25)
    res = ok(client.hub_evaluate(node_id=ids["kr"]))
    assert res["outcome"] == "succeeded"
    progress = ok(client.recipe("kr_progress", {"kr_id": ids["kr"]}))
    assert progress["latest"] == 1300
    assert (
        ok(
            client.hub_ingest(
                {
                    "source_id": "metrics",
                    "external_id": "y",
                    "subject_code": "nope",
                    "type": "metric",
                    "value": 1,
                    "observed_at": now.isoformat(),
                }
            )
        )["status"]
        == "inbox"
    )
    item = ok(client.hub_inbox())["items"][0]
    ok(client.hub_inbox_resolve(item["id"], "dismiss"))
    assert ok(client.hub_inbox())["items"] == []
    assert ok(client.hub_reconcile())["unregistered_codes"] == []


def test_brief(client):
    ids = start_project(client)
    b = ok(client.recipe("start_task_brief", {"task_id": ids["task"]}))
    assert b["goal_chain"]["serves"][0]["goal"]["id"] == ids["kr"]
