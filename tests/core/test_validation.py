"""One fixture per validation rule: a passing and a failing case (spec 11, Testing)."""

import pytest
from florque_graph_core import GraphError, Principal

from tests.conftest import ADMIN, KR_PROPS, World

VIEWER = Principal("val", {"*": "viewer"})
HUB = Principal("hub", {"*": "hub"}, is_agent=True)


def code(fn, *a, **kw):
    with pytest.raises(GraphError) as e:
        fn(*a, **kw)
    return e.value


@pytest.fixture
def w(core):
    return World(core)


def test_class_and_kind(core, w):
    assert (
        code(core.create, ADMIN, "Widget", {"title": "x"}, w.project).code == "ONTOLOGY_VIOLATION"
    )
    assert code(core.create, ADMIN, "Node", {"title": "x"}, w.project).code == "ONTOLOGY_VIOLATION"
    e = code(core.create, ADMIN, "Goal", {"title": "x", "kind": "vision"}, w.project)
    assert e.code == "ONTOLOGY_VIOLATION" and "objective" in e.hint
    assert code(core.create, ADMIN, "Goal", {"title": "x"}, w.project).code == "ONTOLOGY_VIOLATION"


def test_slot_types_and_required(core, w):
    e = code(core.create, ADMIN, "Goal", {**KR_PROPS, "target_value": "lots"}, w.objective)
    assert e.code == "ONTOLOGY_VIOLATION" and e.details["field"] == "target_value"
    assert (
        code(core.create, ADMIN, "Goal", {**KR_PROPS, "window_end": "next week"}, w.objective).code
        == "ONTOLOGY_VIOLATION"
    )
    assert code(core.create, ADMIN, "Goal", {"kind": "objective"}, w.project).details[
        "missing"
    ] == ["title"]
    assert (
        code(
            core.create,
            ADMIN,
            "Goal",
            {"kind": "objective", "title": "x", "colour": "red"},
            w.project,
        ).code
        == "ONTOLOGY_VIOLATION"
    )
    assert (
        code(
            core.create, ADMIN, "Goal", {"kind": "objective", "title": "x", "version": 3}, w.project
        ).code
        == "ONTOLOGY_VIOLATION"
    )
    e = code(core.create, ADMIN, "Document", {"kind": "spec", "title": "API spec"}, w.project)
    assert "uri" in e.details["missing"]


def test_linkml_rule_requires_expectation(core, w):
    props = {k: v for k, v in KR_PROPS.items() if k != "series_code"}
    e = code(core.create, ADMIN, "Goal", props, w.objective)
    assert e.code == "ONTOLOGY_VIOLATION" and e.details["fields"] == ["series_code"]
    # objectives carry the mixin but the rule does not apply
    assert core.create(ADMIN, "Goal", {"kind": "objective", "title": "Be loved"}, w.project)["node"]


def test_edge_typing(core, w):
    e = code(
        core.create,
        ADMIN,
        "WorkItem",
        {"kind": "initiative", "title": "I"},
        w.project,
        [{"type": "serves", "to": w.task}],
    )
    assert e.code == "ONTOLOGY_VIOLATION" and "Goal" in e.hint
    assert code(core.link, ADMIN, w.task, "about", w.kr).code == "ONTOLOGY_VIOLATION"
    assert code(core.link, ADMIN, w.task, "part_of", w.epic).code == "PARENT_RULE"
    assert core.link(ADMIN, w.task, "depends_on", w.epic)["edge"]["rel"] == "DEPENDS_ON"


def test_parent_rules(core, w):
    e = code(core.create, ADMIN, "WorkItem", {"kind": "task", "title": "T"}, w.project)
    assert e.code == "PARENT_RULE" and "WorkItem:epic" in e.hint
    assert (
        code(core.create, ADMIN, "Goal", {**KR_PROPS, "title": "x"}, w.project).code
        == "PARENT_RULE"
    )
    assert (
        code(core.create, ADMIN, "WorkItem", {"kind": "epic", "title": "E"}).code == "PARENT_RULE"
    )
    assert code(core.create, ADMIN, "Project", {"title": "P2"}, w.project).code == "PARENT_RULE"
    e = code(core.create, ADMIN, "WorkItem", {"kind": "initiative", "title": "I"}, w.project)
    assert e.code == "REQUIRED_EDGE"


def test_project_isolation(core, w):
    other = core.create(ADMIN, "Project", {"title": "Other"})["node"]["id"]
    goal = core.create(ADMIN, "Goal", {"kind": "objective", "title": "Elsewhere"}, other)["node"][
        "id"
    ]
    assert code(core.link, ADMIN, w.initiative, "serves", goal).code == "SCOPE_VIOLATION"
    assert code(core.move, ADMIN, w.task, goal).code in ("PARENT_RULE", "SCOPE_VIOLATION")
    # Actor edges may cross projects
    actor = core.create(
        ADMIN,
        "Actor",
        {"kind": "person", "title": "Dana"},
        edges=[
            {"type": "member_of", "to": w.project, "props": {"role": "contributor"}},
            {"type": "member_of", "to": other, "props": {"role": "viewer"}},
        ],
    )["node"]["id"]
    core.link(ADMIN, goal, "owned_by", actor)
    core.link(ADMIN, w.task, "owned_by", actor)
    assert (
        code(core.link, ADMIN, actor, "member_of", other, {"role": "overlord"}).code
        == "ONTOLOGY_VIOLATION"
    )


def test_field_ownership(core, w):
    assert code(core.update, ADMIN, w.kr, {"outcome": "succeeded"}).code == "OWNERSHIP"
    assert code(core.update, HUB, w.kr, {"title": "Hacked"}).code == "OWNERSHIP"
    assert code(core.update, VIEWER, w.task, {"summary": "x"}).code == "OWNERSHIP"
    assert core.update(HUB, w.kr, {"outcome": "pending", "health": "no_data"})["changed"] == [
        "health",
        "outcome",
    ]
    # the hub may not create structure
    assert (
        code(core.create, HUB, "WorkItem", {"kind": "task", "title": "x"}, w.epic).code
        == "FORBIDDEN"
    )
    assert (
        code(core.create, HUB, "Signal", {"kind": "insight", "title": "x"}, w.project).code
        == "FORBIDDEN"
    )
    assert code(core.update, HUB, w.task, {"status": "done"}).code == "OWNERSHIP"


def test_frozen_expectation_definition(core, w):
    e = code(core.update, ADMIN, w.kr, {"target_value": 2000})
    assert e.code == "ONTOLOGY_VIOLATION" and "Archive" in e.hint
    core.update(ADMIN, w.kr, {"summary": "context is fine"})


def test_status_transitions(core, w):
    contributor = Principal("bob", {w.project: "contributor"}, is_agent=True)
    node = core.create(
        contributor, "WorkItem", {"kind": "task", "title": "Agent idea", "status": "active"}, w.epic
    )["node"]
    assert node["status"] == "proposed"  # agent writes start as proposed
    assert code(core.update, contributor, node["id"], {"status": "active"}).code == "FORBIDDEN"
    assert core.update(ADMIN, node["id"], {"status": "active"})["node"]["status"] == "active"
    assert code(core.update, ADMIN, node["id"], {"status": "archived"}).code == "ONTOLOGY_VIOLATION"


def test_non_member_forbidden(core, w):
    stranger = Principal("eve", {"some-other-project": "admin"})
    assert code(core.get, stranger, w.task).code == "FORBIDDEN"
    assert code(core.search, stranger, w.project, "email").code == "FORBIDDEN"
