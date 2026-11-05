"""Spec 5.8 acceptance criteria."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from florque_graph_core import GraphError, Principal
from florque_graph_core.integrity import PART_OF

from tests.conftest import ADMIN, World


def test_rejections(core):
    w = World(core)
    with pytest.raises(GraphError) as e:
        core.create(ADMIN, "WorkItem", {"kind": "task", "title": "t"}, w.project)
    assert e.value.code == "PARENT_RULE"
    with pytest.raises(GraphError) as e:
        core.create(ADMIN, "WorkItem", {"kind": "initiative", "title": "i"}, w.project)
    assert e.value.code == "REQUIRED_EDGE"
    other = core.create(ADMIN, "Project", {"title": "Other"})["node"]["id"]
    og = core.create(ADMIN, "Goal", {"kind": "objective", "title": "x"}, other)["node"]["id"]
    with pytest.raises(GraphError) as e:
        core.link(ADMIN, w.initiative, "serves", og)
    assert e.value.code == "SCOPE_VIOLATION"
    with pytest.raises(GraphError) as e:
        core.update(Principal("v", {"*": "viewer"}), w.task, {"title": "nope"})
    assert e.value.code == "OWNERSHIP"


def test_idempotent_create(core):
    w = World(core)
    a = core.create(
        ADMIN, "WorkItem", {"kind": "task", "title": "Write docs"}, w.epic, idempotency_key="k1"
    )
    b = core.create(
        ADMIN, "WorkItem", {"kind": "task", "title": "Write docs"}, w.epic, idempotency_key="k1"
    )
    assert a["node"]["id"] == b["node"]["id"] and b["replayed"] is True
    nodes = core.list_nodes(ADMIN, w.project, "WorkItem", {"title": "Write docs"})["nodes"]
    assert len(nodes) == 1


def test_parallel_creates_one_dedupe_key(core):
    w = World(core)

    def make(_):
        try:
            return core.create(ADMIN, "WorkItem", {"kind": "task", "title": "Race me"}, w.epic)[
                "node"
            ]["id"]
        except GraphError as e:
            assert e.code == "DUPLICATE_EXACT"
            return None

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(make, range(8)))
    assert len([r for r in results if r]) == 1
    assert len(core.list_nodes(ADMIN, w.project, "WorkItem", {"title": "Race me"})["nodes"]) == 1


def test_duplicate_protocol(core):
    w = World(core)
    with pytest.raises(GraphError) as e:
        core.create(ADMIN, "WorkItem", {"kind": "task", "title": "email  Verification!"}, w.epic)
    assert e.value.code == "DUPLICATE_EXACT" and e.value.details["node"]["id"] == w.task
    with pytest.raises(GraphError) as e:
        core.create(ADMIN, "WorkItem", {"kind": "task", "title": "Email verifications"}, w.epic)
    assert e.value.code == "DUPLICATE_SIMILAR"
    assert e.value.details["candidates"][0]["node"]["id"] == w.task
    assert core.create(
        ADMIN,
        "WorkItem",
        {"kind": "task", "title": "Email verifications"},
        w.epic,
        confirm_new=True,
    )
    # same title under another parent is not a duplicate (dedupe_scope parent)
    epic2 = core.create(ADMIN, "WorkItem", {"kind": "epic", "title": "Login"}, w.initiative)[
        "node"
    ]["id"]
    assert core.create(ADMIN, "WorkItem", {"kind": "task", "title": "Email verification"}, epic2)


def test_integrity_checks(core, graph_store):
    w = World(core)
    assert core.check(ADMIN, w.project) == {"ok": True, "violations": []}

    # seed violations behind the engine's back
    def seed(tx):
        tx.create_node(
            ["WorkItem", "Node"],
            {
                "id": "orphan_task",
                "class": "WorkItem",
                "kind": "task",
                "title": "Orphan",
                "project_id": w.project,
                "status": "active",
                "version": 1,
            },
        )
        tx.create_node(
            ["WorkItem", "Node"],
            {
                "id": "lonely_ini",
                "class": "WorkItem",
                "kind": "initiative",
                "title": "Lonely",
                "project_id": w.project,
                "status": "active",
                "version": 1,
            },
        )
        tx.create_edge(PART_OF, "lonely_ini", w.project)
        tx.create_node(
            ["WorkItem", "Node"],
            {
                "id": "misplaced",
                "class": "WorkItem",
                "kind": "task",
                "title": "Misplaced",
                "project_id": w.project,
                "status": "active",
                "version": 1,
            },
        )
        tx.create_edge(PART_OF, "misplaced", w.project)

    graph_store.write(seed)
    rows = core.check(ADMIN, w.project)["violations"]
    found = {(r["check"], r["node_id"]) for r in rows}
    assert ("workitem_orphan", "orphan_task") in found
    assert ("workitem_initiative_without_serves", "lonely_ini") in found
    assert ("workitem_task_parent_kind", "misplaced") in found


def test_no_orphans_after_start_project_flow(core, hub):
    w = World(core, hub)
    core.create(
        ADMIN,
        "Document",
        {"kind": "spec", "title": "Signup spec", "uri": "s3://b/spec.md"},
        w.project,
        edges=[{"type": "about", "to": w.initiative}],
    )
    assert core.check(ADMIN, w.project)["ok"]
