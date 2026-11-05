import pytest
from florque_signal_hub.store import SQLiteHubStore, StoreConflict


@pytest.fixture
def store():
    s = SQLiteHubStore()
    yield s
    s.close()


def test_ledger_unique_per_tenant_source_external(store):
    store.ledger_insert("src", "e1", {"a": 1})
    with pytest.raises(StoreConflict):
        store.ledger_insert("src", "e1", {"a": 2})
    store.ledger_insert("src", "e2", {"a": 1})
    other = SQLiteHubStore.__new__(SQLiteHubStore)
    other.__dict__.update(store.__dict__)
    other.tenant_id = "t2"
    other.ledger_insert("src", "e1", {"a": 3})  # same key, other tenant


def test_sensor_code_unique_and_reusable_after_archive(store):
    s = store.add_sensor(
        {"series_code": "dau", "project_id": "p", "unit": "u", "aggregation": "last"}
    )
    with pytest.raises(StoreConflict):
        store.add_sensor(
            {"series_code": "dau", "project_id": "p", "unit": "u", "aggregation": "last"}
        )
    store.archive_sensor(s["id"])
    assert store.sensor_by_code("dau") is None
    store.add_sensor({"series_code": "dau", "project_id": "p", "unit": "u", "aggregation": "last"})


def test_job_claim_is_exclusive_and_leased(store):
    store.enqueue("evaluate", {})
    job = store.claim("w1", lease_seconds=60)
    assert job and job["worker_id"] == "w1" and job["attempts"] == 1
    assert store.claim("w2", lease_seconds=60) is None
    store.fail(job["id"], "boom", retry_after_seconds=0)
    again = store.claim("w2", lease_seconds=60)
    assert again["id"] == job["id"] and again["attempts"] == 2
    store.complete(again["id"])
    assert store.claim("w3", lease_seconds=60) is None


def test_expired_lease_is_reclaimed(store):
    store.enqueue("evaluate", {})
    store.claim("w1", lease_seconds=-1)  # lease already expired
    assert store.claim("w2", lease_seconds=60)["worker_id"] == "w2"
