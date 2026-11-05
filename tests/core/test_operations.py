import pytest
from florque_graph_core import GraphError

from tests.conftest import ADMIN, World


@pytest.fixture
def w(core):
    return World(core)


def test_get_returns_chain_and_neighbours(core, w):
    out = core.get(ADMIN, w.task, depth=2)
    assert [a["id"] for a in out["ancestors"]] == [w.epic, w.initiative, w.project]
    assert w.epic in out["neighbours"]
    assert "dedupe_key" not in out["node"]


def test_update_versioning(core, w):
    n = core.update(ADMIN, w.task, {"summary": "first"}, if_version=1)["node"]
    assert n["version"] == 2
    with pytest.raises(GraphError) as e:
        core.update(ADMIN, w.task, {"summary": "stale"}, if_version=1)
    assert e.value.code == "VERSION_CONFLICT" and e.value.details["current_version"] == 2
    # no-op patches do not bump the version
    assert core.update(ADMIN, w.task, {"summary": "first"})["changed"] == []
    # lists are additive
    core.update(ADMIN, w.task, {"sources": ["https://a"]})
    assert core.update(ADMIN, w.task, {"sources": ["https://b"]})["node"]["sources"] == [
        "https://a",
        "https://b",
    ]


def test_update_title_checks_duplicates(core, w):
    t2 = core.create(ADMIN, "WorkItem", {"kind": "task", "title": "Password reset"}, w.epic)[
        "node"
    ]["id"]
    with pytest.raises(GraphError) as e:
        core.update(ADMIN, t2, {"title": "Email verification"})
    assert e.value.code == "DUPLICATE_EXACT"


def test_archive_and_cascade(core, w):
    with pytest.raises(GraphError) as e:
        core.archive(ADMIN, w.epic)
    assert e.value.code == "PARENT_RULE"
    out = core.archive(ADMIN, w.epic, cascade=True)
    assert set(out["archived"]) == {w.epic, w.task}
    # the dedupe key is released, so the title can be reused
    assert core.create(ADMIN, "WorkItem", {"kind": "epic", "title": "Signup flow"}, w.initiative)


def test_move(core, w):
    epic2 = core.create(ADMIN, "WorkItem", {"kind": "epic", "title": "Activation"}, w.initiative)[
        "node"
    ]["id"]
    core.move(ADMIN, w.task, epic2)
    assert core.get(ADMIN, w.task, 0)["ancestors"][0]["id"] == epic2
    with pytest.raises(GraphError) as e:
        core.move(ADMIN, w.epic, w.task)
    assert e.value.code == "PARENT_RULE"


def test_unlink_keeps_required_edge(core, w):
    with pytest.raises(GraphError) as e:
        core.unlink(ADMIN, w.initiative, "serves", w.kr)
    assert e.value.code == "REQUIRED_EDGE"
    core.link(ADMIN, w.initiative, "serves", w.objective)
    core.unlink(ADMIN, w.initiative, "serves", w.kr)


def test_merge(core, w):
    dup = core.create(
        ADMIN,
        "WorkItem",
        {
            "kind": "task",
            "title": "Verify email address",
            "summary": "dup",
            "sources": ["slack://x"],
        },
        w.epic,
    )["node"]["id"]
    doc = core.create(
        ADMIN,
        "Document",
        {"kind": "spec", "title": "Spec", "uri": "s3://spec"},
        w.project,
        edges=[{"type": "about", "to": dup}],
    )["node"]["id"]
    out = core.merge(ADMIN, w.task, dup)
    assert "Verify email address" in out["node"]["aliases"]
    assert out["node"]["sources"] == ["slack://x"]
    assert any(e["dst"] == w.task for e in core.get(ADMIN, doc, 1)["edges"] if e["rel"] == "ABOUT")
    assert core.get(ADMIN, dup, 0)["node"]["status"] == "archived"


def test_merge_conflict(core, w):
    a = core.create(ADMIN, "Document", {"kind": "spec", "title": "A", "uri": "s3://a"}, w.project)[
        "node"
    ]["id"]
    b = core.create(ADMIN, "Document", {"kind": "spec", "title": "B", "uri": "s3://b"}, w.project)[
        "node"
    ]["id"]
    with pytest.raises(GraphError) as e:
        core.merge(ADMIN, a, b)
    assert e.value.code == "MERGE_CONFLICT" and "uri" in e.value.details["fields"]


def test_changes_log(core, w):
    rows = core.changes(ADMIN, w.project)["changes"]
    assert [r["op"] for r in rows][:2] == ["create", "create"]
    since = core.changes(ADMIN, w.project)["cursor"]
    core.update(ADMIN, w.task, {"summary": "s"})
    newer = core.changes(ADMIN, w.project, since)["changes"]
    assert [r["op"] for r in newer] == ["update"]


def test_search(core, w):
    res = core.search(ADMIN, w.project, "email verify")["results"]
    assert res[0]["node"]["id"] == w.task


def test_find_by_mixin(core, w):
    nodes = core.find_by_mixin(ADMIN, "Expectation", {"series_code": "dau"})["nodes"]
    assert [n["id"] for n in nodes] == [w.kr]
    with pytest.raises(GraphError):
        core.find_by_mixin(ADMIN, "Goal")


def test_describe(core):
    d = core.describe()
    assert d["ontology_version"] == "0.2.0" and "Ontology card" in d["card"]
