"""Recipe implementations. Each returns one bundle so agents make few calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from florque_graph_core import GraphCore, Principal
from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.validation.values import parse_datetime

STALE_PROPOSED_DAYS = 14
TREND_POINTS = 12


class Reader:
    """Thin read facade over GraphCore for one principal."""

    def __init__(self, core: GraphCore, principal: Principal) -> None:
        self.core = core
        self.p = principal

    def node(self, node_id: str) -> dict[str, Any]:
        return self.core.get(self.p, node_id, depth=0)["node"]

    def ancestors(self, node_id: str) -> list[dict[str, Any]]:
        return self.core.get(self.p, node_id, depth=0)["ancestors"]

    def nodes(
        self, project_id: str, cls: str | None = None, **filters: Any
    ) -> list[dict[str, Any]]:
        return self.core.list_nodes(self.p, project_id, cls, filters)["nodes"]

    def edges(
        self, node_id: str, edge: str | None = None, direction: str = "out"
    ) -> list[dict[str, Any]]:
        return self.core.edges_of(self.p, node_id, edge, direction)["edges"]

    def children(self, node_id: str) -> list[dict[str, Any]]:
        return [
            e["node"]
            for e in self.edges(node_id, "part_of", "in")
            if e["node"].get("status") != "archived"
        ]

    def now(self) -> datetime:
        return self.core.clock()


def _brief(n: dict[str, Any], *extra: str) -> dict[str, Any]:
    keys = ("id", "class", "kind", "title", "status", *extra)
    return {k: n[k] for k in keys if k in n}


KR_FIELDS = (
    "series_code",
    "comparator",
    "target_value",
    "target_upper",
    "unit",
    "baseline_value",
    "window_start",
    "window_end",
    "outcome",
    "health",
    "last_value",
    "last_observed_at",
)


# ---------------------------------------------------------------- project_overview


def project_overview(r: Reader, project_id: str) -> dict[str, Any]:
    project = r.node(project_id)
    goals = r.nodes(project_id, "Goal")
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for g in goals:
        if g.get("kind") == "key_result":
            for e in r.edges(g["id"], "part_of", "out"):
                by_parent.setdefault(e["dst"], []).append(g)
    objectives = [
        {
            **_brief(o, "summary"),
            "key_results": [_brief(k, *KR_FIELDS) for k in by_parent.get(o["id"], [])],
        }
        for o in goals
        if o.get("kind") == "objective"
    ]
    initiatives = []
    for i in r.nodes(project_id, "WorkItem", kind="initiative"):
        if i.get("status") not in ("active", "proposed"):
            continue
        serves = [e["dst"] for e in r.edges(i["id"], "serves", "out")]
        initiatives.append({**_brief(i), "serves": serves})
    return {
        "project": _brief(project, "summary"),
        "objectives": objectives,
        "initiatives": initiatives,
    }


# ---------------------------------------------------------------- why


def why(r: Reader, node_id: str) -> dict[str, Any]:
    node = r.node(node_id)
    chain = [node, *r.ancestors(node_id)]
    goal_ids: list[str] = []
    for n in chain:
        if n.get("class") == "Goal":
            goal_ids.append(n["id"])
        for e in r.edges(n["id"], "serves", "out"):
            goal_ids.append(e["dst"])
        if n.get("class") in ("Document", "Signal"):
            for e in r.edges(n["id"], "about", "out"):
                if e["node"].get("class") == "Goal":
                    goal_ids.append(e["dst"])
                elif e["node"].get("class") == "WorkItem":
                    goal_ids.extend(g["id"] for g in _served_goals(r, e["dst"]))
    served = []
    for gid in dict.fromkeys(goal_ids):
        g = r.node(gid)
        entry = {"goal": _brief(g, *KR_FIELDS)}
        if g.get("kind") == "key_result":
            anc = r.ancestors(gid)
            if anc:
                entry["objective"] = _brief(anc[0])
        served.append(entry)
    return {
        "node": _brief(node, "summary"),
        "chain": [_brief(n) for n in chain[1:]],
        "serves": served,
    }


def _served_goals(r: Reader, node_id: str) -> list[dict[str, Any]]:
    chain = [r.node(node_id), *r.ancestors(node_id)]
    out: list[dict[str, Any]] = []
    for n in chain:
        out.extend(e["node"] for e in r.edges(n["id"], "serves", "out"))
    return out


# ---------------------------------------------------------------- kr_progress


def _metric_points(r: Reader, kr: dict[str, Any]) -> list[dict[str, Any]]:
    pts = [
        s
        for s in r.nodes(
            kr["project_id"], "Signal", kind="metric", series_code=kr.get("series_code")
        )
        if s.get("unit") == kr.get("unit")
    ]
    pts.sort(key=lambda s: s.get("observed_at", ""))
    return pts


def kr_progress(r: Reader, kr_id: str) -> dict[str, Any]:
    kr = r.node(kr_id)
    if kr.get("kind") != "key_result":
        raise GraphError(
            ErrorCode.ONTOLOGY_VIOLATION,
            f"{kr_id} is not a key result",
            hint="Pass a Goal:key_result id.",
        )
    pts = _metric_points(r, kr)
    latest = pts[-1] if pts else None
    baseline = kr.get("baseline_value")
    target = kr.get("target_value")
    progress = None
    value = latest.get("numeric_value") if latest else kr.get("last_value")
    if value is not None and baseline is not None and target is not None and target != baseline:
        progress = round(max(0.0, min(1.0, (value - baseline) / (target - baseline))), 3)
    staleness = None
    if latest and latest.get("observed_at"):
        staleness = (r.now() - parse_datetime(latest["observed_at"])).days
    trend: list[dict[str, Any]] = [
        {
            "period": p.get("period"),
            "value": p.get("numeric_value"),
            "observed_at": p.get("observed_at"),
        }
        for p in pts[-TREND_POINTS:]
    ]
    slope = None
    if len(trend) >= 2:
        first, last = trend[0], trend[-1]
        days = (
            parse_datetime(last["observed_at"]) - parse_datetime(first["observed_at"])
        ).total_seconds() / 86400
        if days > 0:
            slope = round((last["value"] - first["value"]) / days, 4)
    return {
        "kr": _brief(kr, *KR_FIELDS),
        "baseline": baseline,
        "latest": value,
        "progress": progress,
        "trend": trend,
        "slope_per_day": slope,
        "staleness_days": staleness,
    }


# ---------------------------------------------------------------- start_task_brief


def start_task_brief(r: Reader, task_id: str) -> dict[str, Any]:
    task = r.node(task_id)
    if task.get("class") != "WorkItem":
        raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{task_id} is not a WorkItem")
    w = why(r, task_id)
    chain = [task, *r.ancestors(task_id)]
    subject_ids = {n["id"] for n in chain} | {s["goal"]["id"] for s in w["serves"]}

    documents, feedback = [], []
    for sid in subject_ids:
        for e in r.edges(sid, "about", "in"):
            n = e["node"]
            if n.get("status") == "archived":
                continue
            if n.get("class") == "Document":
                documents.append(_brief(n, "uri", "summary"))
            elif n.get("class") == "Signal" and n.get("kind") in (
                "feedback",
                "incident",
                "research",
                "insight",
            ):
                feedback.append(_brief(n, "summary", "observed_at"))

    # past debrief lessons: debriefs about other work under the same initiative
    initiative = next((n for n in chain if n.get("kind") == "initiative"), None)
    lessons = []
    if initiative:
        stack, seen = [initiative["id"]], set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(c["id"] for c in r.children(cur) if c.get("class") == "WorkItem")
        for wid in seen - {task_id}:
            for e in r.edges(wid, "about", "in"):
                n = e["node"]
                if (
                    n.get("class") == "Signal"
                    and n.get("kind") == "debrief"
                    and n.get("status") != "archived"
                ):
                    lessons.append({**_brief(n, "summary"), "about": wid})

    owner = None
    for n in chain:
        es = r.edges(n["id"], "owned_by", "out")
        if es:
            owner = {
                **_brief(es[0]["node"]),
                "inherited_from": None if n["id"] == task_id else n["id"],
            }
            break
    depends_on = [_brief(e["node"]) for e in r.edges(task_id, "depends_on", "out")]
    return {
        "task": _brief(task, "summary"),
        "goal_chain": w,
        "documents": _uniq(documents),
        "feedback": _uniq(feedback),
        "lessons": _uniq(lessons),
        "owner": owner,
        "depends_on": depends_on,
    }


def _uniq(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({i["id"]: i for i in items}.values())


# ---------------------------------------------------------------- hygiene


def hygiene(r: Reader, project_id: str, stale_days: int = STALE_PROPOSED_DAYS) -> dict[str, Any]:
    initiatives_serving_nothing = [
        _brief(i)
        for i in r.nodes(project_id, "WorkItem", kind="initiative")
        if not r.edges(i["id"], "serves", "out")
    ]
    krs_incomplete = [
        _brief(k)
        for k in r.nodes(project_id, "Goal", kind="key_result")
        if not k.get("series_code") or k.get("target_value") is None
    ]
    cutoff = r.now() - timedelta(days=int(stale_days))
    stale = [
        _brief(n, "created_at")
        for n in r.nodes(project_id, status="proposed")
        if n.get("created_at") and parse_datetime(n["created_at"]) < cutoff
    ]
    krs_unserved = [
        _brief(k)
        for k in r.nodes(project_id, "Goal", kind="key_result")
        if not r.edges(k["id"], "serves", "in")
        and not any(
            r.edges(o["id"], "serves", "in")
            for o in r.ancestors(k["id"])
            if o.get("class") == "Goal"
        )
    ]
    integrity = r.core.check(r.p, project_id)
    return {
        "initiatives_serving_nothing": initiatives_serving_nothing,
        "krs_without_series_or_target": krs_incomplete,
        "krs_without_initiatives": krs_unserved,
        "stale_proposed": stale,
        "integrity_violations": integrity["violations"],
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------- deferred (impact module, M5)


def blast_radius(r: Reader, task_id: str) -> dict[str, Any]:
    raise GraphError(
        ErrorCode.NOT_FOUND,
        "blast_radius needs the workgraph-impact module (Components), which is not loaded",
        hint="Enable the impact module once Components are modelled.",
    )


def recurring_issues(r: Reader, scope: str) -> dict[str, Any]:
    raise GraphError(
        ErrorCode.NOT_FOUND,
        "recurring_issues needs debrief analysis (milestone M5)",
        hint="Use hygiene or start_task_brief for now.",
    )
