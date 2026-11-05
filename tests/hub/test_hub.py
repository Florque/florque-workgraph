from datetime import timedelta

import pytest
from florque_graph_core import GraphError, Principal
from florque_signal_hub import ContractError, SignalHub, SQLiteHubStore
from florque_signal_hub.contract import verify_contract

from tests.conftest import ADMIN, KR_PROPS, World


def metric(n, value, when, code="dau", **kw):
    return {
        "source_id": "metrics",
        "external_id": f"m{n}",
        "subject_code": code,
        "type": "metric",
        "value": value,
        "observed_at": when.isoformat(),
        **kw,
    }


def test_contract_verified(core):
    c = verify_contract(core.describe())
    assert (c.expectation_class, c.observation_class) == ("Goal", "Signal")


def test_contract_mismatch_refuses_start(core):
    d = core.describe()
    del d["classes"]["Goal"]["fields"]["outcome"]
    d["classes"]["Signal"]["fields"]["observed_at"]["type"] = "str"
    with pytest.raises(ContractError) as e:
        verify_contract(d)
    assert len(e.value.problems) == 2
    d = core.describe()
    d["mixins_version"] = "1.0.0"
    with pytest.raises(ContractError):
        verify_contract(d)


def test_kr_creation_needs_registered_series(core, hub):
    w = World(core, hub)
    with pytest.raises(GraphError) as e:
        core.create(
            ADMIN,
            "Goal",
            {**KR_PROPS, "title": "Retention", "series_code": "d30_retention"},
            w.objective,
        )
    assert e.value.code == "ONTOLOGY_VIOLATION" and "sensor" in e.value.hint
    with pytest.raises(GraphError) as e:
        core.create(ADMIN, "Goal", {**KR_PROPS, "title": "DAU in k", "unit": "kusers"}, w.objective)
    assert "unit" in e.value.message


def test_series_flips_kr_succeeded_idempotently(core, hub, clock):
    w = World(core, hub)
    start = clock.now
    for i, v in enumerate([400, 700, 1100]):
        out = hub.ingest(hub.principal, metric(i, v, start - timedelta(days=2 - i)))
        assert out["status"] == "accepted"
    kr = core.get(ADMIN, w.kr, 0)["node"]
    assert (kr["outcome"], kr["health"], kr["last_value"]) == ("pending", "on_track", 1100)

    clock.now = start + timedelta(days=23)  # Dec 3: window + grace closed
    out = hub.evaluate_one(w.kr)
    assert out["outcome"] == "succeeded"
    version = core.get(ADMIN, w.kr, 0)["node"]["version"]

    # replay: same observations, same result, no new writes
    for i, v in enumerate([400, 700, 1100]):
        assert (
            hub.ingest(hub.principal, metric(i, v, start - timedelta(days=2 - i)))["status"]
            == "duplicate"
        )
    assert hub.evaluate_one(w.kr)["changed"] == []
    assert core.get(ADMIN, w.kr, 0)["node"]["version"] == version
    events = hub.store.events_since(None)
    assert [e["payload"]["to"] for e in events] == ["pending", "succeeded"]


def test_series_flips_kr_failed_and_correction_reevaluates(core, hub, clock):
    w = World(core, hub)
    when = clock.now
    hub.ingest(hub.principal, metric(1, 900, when, period="2026-11-10"))
    clock.now = when + timedelta(days=23)
    assert hub.evaluate_one(w.kr)["outcome"] == "failed"

    # a corrected value for the same period writes a new revision and re-evaluates
    out = hub.ingest(hub.principal, metric(2, 1200, when, period="2026-11-10"))
    assert out["status"] == "corrected"
    assert out["evaluations"][0]["outcome"] == "succeeded"
    new = core.get(ADMIN, out["signal_id"], 0)["node"]
    old = core.get(ADMIN, out["superseded"], 0)["node"]
    assert (new["revision"], old["status"]) == (2, "archived")
    assert hub.store.audit_list(action="metric.correction")


def test_expired_with_no_data(core, hub, clock):
    w = World(core, hub)
    clock.now += timedelta(days=30)
    out = hub.evaluate_all(w.project)
    assert out["results"][0]["outcome"] == "expired"


def test_unmatched_goes_to_inbox(core, hub, clock):
    World(core, hub)
    out = hub.ingest(hub.principal, metric(9, 1, clock.now, code="unknown_series"))
    assert out["status"] == "inbox" and out["reason"] == "unregistered_code"
    out = hub.ingest(
        hub.principal,
        {
            "source_id": "slack",
            "external_id": "t1",
            "type": "feedback",
            "summary": "users love it",
            "observed_at": clock.now.isoformat(),
        },
    )
    assert out["reason"] == "unknown_source"
    assert len(hub.inbox(ADMIN)["items"]) == 2


def test_inbox_attach(core, hub, clock):
    w = World(core, hub)
    hub.add_source(ADMIN, "slack", "slack")
    out = hub.ingest(
        hub.principal,
        {
            "source_id": "slack",
            "external_id": "t1",
            "type": "feedback",
            "summary": "signup email never arrives",
            "observed_at": clock.now.isoformat(),
        },
    )
    item = out["inbox_id"]
    res = hub.resolve_inbox(ADMIN, item, "attach", w.task)
    sig = core.get(ADMIN, res["signal_id"], 1)
    assert sig["node"]["kind"] == "feedback"
    assert any(e["rel"] == "ABOUT" and e["dst"] == w.task for e in sig["edges"])
    assert hub.inbox(ADMIN)["items"] == []


def test_non_metric_signal_about_kr(core, hub, clock):
    w = World(core, hub)
    out = hub.ingest(
        hub.principal,
        {
            "source_id": "metrics",
            "external_id": "inc1",
            "subject_code": "dau",
            "type": "incident",
            "title": "DAU pipeline outage",
            "payload_ref": "https://status/1",
            "observed_at": clock.now.isoformat(),
        },
    )
    sig = core.get(ADMIN, out["signal_id"], 1)
    assert sig["node"]["kind"] == "incident" and sig["node"]["sources"] == ["https://status/1"]
    assert any(e["dst"] == w.kr for e in sig["edges"])


def test_hub_permissions_enforced_by_core(core, hub, clock):
    w = World(core, hub)
    hp = hub.principal
    with pytest.raises(GraphError) as e:
        core.update(hp, w.kr, {"target_value": 5})
    assert e.value.code == "OWNERSHIP"
    with pytest.raises(GraphError) as e:
        core.create(hp, "WorkItem", {"kind": "task", "title": "x"}, w.epic)
    assert e.value.code == "FORBIDDEN"
    with pytest.raises(GraphError):
        core.update(hp, w.task, {"status": "done"})
    with pytest.raises(GraphError) as e:
        hub.ingest(Principal("bob", {"*": "contributor"}), metric(1, 5, clock.now))
    assert e.value.code == "FORBIDDEN"


def test_registry_needs_admin(core, hub):
    w = World(core, hub)
    contributor = Principal("bob", {w.project: "contributor"})
    with pytest.raises(GraphError) as e:
        hub.add_sensor(contributor, "mau", w.project, "users")
    assert e.value.code == "FORBIDDEN"
    with pytest.raises(GraphError) as e:
        hub.add_sensor(ADMIN, "dau", w.project, "users")
    assert e.value.code == "DUPLICATE_EXACT"


def test_reconcile_flags_and_never_deletes(core, hub):
    w = World(core, hub)
    hub.add_sensor(ADMIN, "mau", w.project, "users")
    th = hub.add_binding(
        ADMIN, "thread", {"source_id": "metrics", "thread_ref": "C1/123", "node_id": w.task}
    )
    core.archive(ADMIN, w.task)
    report = hub.reconcile()
    assert report["unused_sensors"] == ["mau"]
    assert report["archived_bindings"] == [th["binding"]["id"]]
    sensors = {s["series_code"]: s for s in hub.store.list_sensors()}
    assert sensors["mau"]["flag"] == "unused" and sensors["dau"]["flag"] is None
    assert hub.store.list_bindings("thread", include_archived=True)


def test_jobs_lease_and_retry(core, hub):
    World(core, hub)
    hub.enqueue("evaluate")
    hub.enqueue("reconcile")
    out = hub.run_jobs_once("w1")
    assert [j["kind"] for j in out["jobs"]] == ["evaluate", "reconcile"]
    assert hub.run_jobs_once("w1")["jobs"] == []


def test_hub_store_shared_contract_on_restart(core, tmp_path):
    path = str(tmp_path / "hub.sqlite")
    s1 = SQLiteHubStore(path)
    s1.add_source("metrics", "sensor", None, {})
    s1.close()
    s2 = SQLiteHubStore(path)
    assert s2.migrate() == []  # migrations are idempotent
    assert s2.get_source("metrics")
    SignalHub(core, s2)
    s2.close()
