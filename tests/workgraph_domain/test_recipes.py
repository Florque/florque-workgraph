from datetime import timedelta

import pytest
from florque_graph_core import GraphError
from florque_workgraph_domain.recipes import run_recipe

from tests.conftest import ADMIN, World


def test_project_overview(core, hub):
    w = World(core, hub)
    out = run_recipe(core, ADMIN, "project_overview", {"project_id": w.project})
    assert out["objectives"][0]["key_results"][0]["id"] == w.kr
    assert out["initiatives"][0]["serves"] == [w.kr]


def test_why_and_brief(core, hub):
    w = World(core, hub)
    doc = core.create(
        ADMIN,
        "Document",
        {"kind": "design", "title": "Signup design", "uri": "s3://d"},
        w.project,
        edges=[{"type": "about", "to": w.epic}],
    )["node"]["id"]
    sibling = core.create(ADMIN, "WorkItem", {"kind": "task", "title": "Captcha"}, w.epic)["node"][
        "id"
    ]
    core.create(
        ADMIN,
        "Signal",
        {"kind": "debrief", "title": "Captcha debrief", "summary": "Took 2x estimate"},
        w.project,
        edges=[{"type": "about", "to": sibling}],
    )
    actor = core.create(
        ADMIN,
        "Actor",
        {"kind": "person", "title": "Dana"},
        edges=[{"type": "member_of", "to": w.project, "props": {"role": "contributor"}}],
    )["node"]["id"]
    core.link(ADMIN, w.initiative, "owned_by", actor)

    why = run_recipe(core, ADMIN, "why", {"node_id": w.task})
    assert [g["goal"]["id"] for g in why["serves"]] == [w.kr]
    assert why["serves"][0]["objective"]["id"] == w.objective

    brief = run_recipe(core, ADMIN, "start_task_brief", {"task_id": w.task})
    assert [d["id"] for d in brief["documents"]] == [doc]
    assert brief["lessons"][0]["title"] == "Captcha debrief"
    assert brief["owner"]["id"] == actor and brief["owner"]["inherited_from"] == w.initiative


def test_kr_progress(core, hub, clock):
    w = World(core, hub)
    for i, v in enumerate([300, 500, 700]):
        hub.ingest(
            hub.principal,
            {
                "source_id": "metrics",
                "external_id": f"p{i}",
                "subject_code": "dau",
                "type": "metric",
                "value": v,
                "observed_at": (clock.now - timedelta(days=3 - i)).isoformat(),
            },
        )
    out = run_recipe(core, ADMIN, "kr_progress", {"kr_id": w.kr})
    assert out["latest"] == 700 and out["progress"] == 0.625
    assert len(out["trend"]) == 3 and out["slope_per_day"] == 200
    assert out["staleness_days"] == 1


def test_hygiene(core, hub, clock):
    w = World(core, hub)
    clock.now += timedelta(days=30)
    out = run_recipe(core, ADMIN, "hygiene", {"project_id": w.project})
    assert {n["id"] for n in out["stale_proposed"]} >= {w.objective, w.task}
    assert out["initiatives_serving_nothing"] == []


def test_unknown_recipe_and_missing_args(core):
    with pytest.raises(GraphError) as e:
        run_recipe(core, ADMIN, "nope", {})
    assert e.value.code == "NOT_FOUND"
    with pytest.raises(GraphError) as e:
        run_recipe(core, ADMIN, "why", {})
    assert "node_id" in e.value.hint
