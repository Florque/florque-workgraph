"""Signal hub per tenant: registry, ingestion, inbox and evaluation never mix tenants."""

from __future__ import annotations

import pytest
from florque_graph_core import GraphCore, GraphError, Principal
from florque_signal_hub import SignalHub

from tests.conftest import KR_PROPS

A = Principal("ann", {"*": "admin"}, can_create_projects=True, tenant_id="t_a")
B = Principal("bob", {"*": "admin"}, can_create_projects=True, tenant_id="t_b")
INGEST_A = Principal("ingest-a", {"*": "hub"}, is_agent=True, tenant_id="t_a")


def seed(core: GraphCore, hub: SignalHub, p: Principal) -> dict[str, str]:
    pid = core.create(p, "Project", {"title": "Checkout"})["node"]["id"]
    obj = core.create(p, "Goal", {"kind": "objective", "title": "Grow"}, pid)["node"]["id"]
    hub.add_source(p, "metrics", "sensor")  # same source id in both tenants
    hub.add_sensor(p, "dau", pid, "users", source_id="metrics")  # same series code too
    kr = core.create(p, "Goal", KR_PROPS, obj)["node"]["id"]
    return {"project": pid, "kr": kr}


def obs(external_id: str, value: float, code: str = "dau") -> dict[str, object]:
    return {
        "source_id": "metrics",
        "external_id": external_id,
        "subject_code": code,
        "type": "metric",
        "value": value,
        "observed_at": "2026-11-09T10:00:00Z",
    }


def test_registry_is_per_tenant(core, hub):
    a = seed(core, hub, A)
    b = seed(core, hub, B)
    assert [s["project_id"] for s in hub.list_sensors(A)["sensors"]] == [a["project"]]
    assert [s["project_id"] for s in hub.list_sensors(B)["sensors"]] == [b["project"]]
    with pytest.raises(GraphError) as e:
        hub.add_sensor(A, "other", b["project"], "users")
    assert e.value.code in ("FORBIDDEN", "NOT_FOUND")


def test_ingest_routes_inside_the_tenant(core, hub):
    a = seed(core, hub, A)
    b = seed(core, hub, B)
    out = hub.ingest(INGEST_A, obs("m1", 1200))
    assert out["status"] == "accepted"
    assert [ev["node_id"] for ev in out["evaluations"]] == [a["kr"]]
    assert core.get(A, a["kr"])["node"]["last_value"] == 1200
    assert "last_value" not in core.get(B, b["kr"])["node"]
    signal = core.get(A, out["signal_id"])["node"]
    assert signal["tenant_id"] == "t_a"
    # the same external id in another tenant is a different observation
    ingest_b = Principal("ingest-b", {"*": "hub"}, is_agent=True, tenant_id="t_b")
    assert hub.ingest(ingest_b, obs("m1", 900))["status"] == "accepted"
    assert hub.ingest(INGEST_A, obs("m1", 1200))["status"] == "duplicate"


def test_inbox_is_per_tenant(core, hub):
    seed(core, hub, A)
    seed(core, hub, B)
    out = hub.ingest(INGEST_A, obs("m2", 5, code="unknown"))
    assert out["status"] == "inbox"
    assert len(hub.inbox(A)["items"]) == 1
    assert hub.inbox(B)["items"] == []
    with pytest.raises(GraphError) as e:
        hub.resolve_inbox(B, out["inbox_id"], "dismiss")
    assert e.value.code == "NOT_FOUND"


def test_kr_hook_checks_the_tenants_sensors(core, hub):
    a = seed(core, hub, A)
    b_pid = core.create(B, "Project", {"title": "Other"})["node"]["id"]
    b_obj = core.create(B, "Goal", {"kind": "objective", "title": "O"}, b_pid)["node"]["id"]
    with pytest.raises(GraphError) as e:  # "dau" is registered in tenant A only
        core.create(B, "Goal", {**KR_PROPS, "title": "B KR"}, b_obj)
    assert e.value.code == "ONTOLOGY_VIOLATION"
    assert a


def test_reconcile_reports_per_tenant(core, hub):
    seed(core, hub, A)
    seed(core, hub, B)
    hub.add_sensor(B, "spare", core.list_projects(B)["projects"][0]["id"], "users")
    report = hub.reconcile()
    assert report["tenants"]["t_a"]["unused_sensors"] == []
    assert report["tenants"]["t_b"]["unused_sensors"] == ["spare"]
