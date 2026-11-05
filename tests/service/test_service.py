from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from florque_client import build_app
from florque_graph_core.store.memory import MemoryStore
from florque_service import TokenStore, create_app
from florque_signal_hub import SQLiteHubStore


@pytest.fixture
def svc() -> Iterator[tuple[TestClient, TokenStore]]:
    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore())
    tokens = TokenStore()
    with TestClient(create_app(app, tokens, scheduler=False)) as tc:
        yield tc, tokens


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_probes_and_public_ontology(svc):
    tc, _ = svc
    assert tc.get("/healthz").json() == {"ok": True}
    assert tc.get("/readyz").json()["ok"] is True
    assert tc.get("/v1/ontology").json()["data"]["ontology_version"] == "0.2.0"
    assert "/v1/nodes" in tc.get("/openapi.json").json()["paths"]


def test_unauthenticated_and_revoked(svc):
    tc, tokens = svc
    r = tc.get("/v1/nodes/x")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    issued = tokens.issue("alice", {"*": "admin"})
    assert tc.get("/v1/nodes/x", headers=auth(issued["token"])).status_code == 404
    tokens.revoke(issued["id"])
    assert tc.get("/v1/nodes/x", headers=auth(issued["token"])).status_code == 401
    assert tc.get("/v1/nodes/x", headers=auth(issued["token"][:-2] + "zz")).status_code == 401


def test_roles_enforced_server_side(svc):
    tc, tokens = svc
    admin = tokens.issue("alice", {"*": "admin"}, can_create_projects=True)["token"]
    r = tc.post("/v1/projects", json={"props": {"title": "P"}}, headers=auth(admin))
    assert r.status_code == 201
    pid = r.json()["data"]["node"]["id"]
    viewer = tokens.issue("val", {pid: "viewer"})["token"]
    r = tc.post(
        "/v1/nodes",
        json={"cls": "Goal", "props": {"kind": "objective", "title": "G"}, "parent_id": pid},
        headers=auth(viewer),
    )
    assert r.status_code == 403
    assert (
        tc.post("/v1/projects", json={"props": {"title": "Q"}}, headers=auth(viewer)).status_code
        == 403
    )
    agent = tokens.issue("bot", {pid: "contributor"}, is_agent=True)["token"]
    r = tc.post(
        "/v1/nodes",
        json={
            "cls": "Goal",
            "props": {"kind": "objective", "title": "G", "status": "active"},
            "parent_id": pid,
        },
        headers=auth(agent),
    )
    assert r.status_code == 201 and r.json()["data"]["node"]["status"] == "proposed"
    outsider = tokens.issue("eve", {"other": "admin"})["token"]
    assert tc.get(f"/v1/nodes/{pid}", headers=auth(outsider)).status_code == 403


def test_idempotency_header_and_validation(svc):
    tc, tokens = svc
    admin = auth(tokens.issue("alice", {"*": "admin"}, can_create_projects=True)["token"])
    pid = tc.post("/v1/projects", json={"props": {"title": "P"}}, headers=admin).json()["data"][
        "node"
    ]["id"]
    body = {"cls": "Goal", "props": {"kind": "objective", "title": "G"}, "parent_id": pid}
    a = tc.post("/v1/nodes", json=body, headers={**admin, "Idempotency-Key": "k"}).json()
    b = tc.post("/v1/nodes", json=body, headers={**admin, "Idempotency-Key": "k"}).json()
    assert a["data"]["node"]["id"] == b["data"]["node"]["id"]
    r = tc.post("/v1/nodes", json={"props": {}}, headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ONTOLOGY_VIOLATION"
    assert "florque_validation_failures_total" in tc.get("/metrics").text
    assert r.headers.get("X-Request-ID")


def test_token_cli(tmp_path, monkeypatch, capsys):
    from florque_service.app import main

    monkeypatch.setenv("FLORQUE_SERVICE_DB", str(tmp_path / "svc.sqlite"))
    main(["token", "issue", "--actor", "alice", "--role", "*=admin", "--create-projects"])
    out = capsys.readouterr().out
    assert '"token": "fwg_' in out
    store = TokenStore(str(tmp_path / "svc.sqlite"))
    assert store.list()[0]["actor_id"] == "alice"
