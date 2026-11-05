"""Recipes: one context bundle per call (spec 2). Pure Python over graph-core read operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from florque_graph_core import GraphCore, Principal
from florque_graph_core.errors import ErrorCode, GraphError

from florque_workgraph_domain.recipes import bundles

Recipe = Callable[..., dict[str, Any]]

RECIPES: dict[str, tuple[Recipe, tuple[str, ...]]] = {
    "project_overview": (bundles.project_overview, ("project_id",)),
    "why": (bundles.why, ("node_id",)),
    "kr_progress": (bundles.kr_progress, ("kr_id",)),
    "start_task_brief": (bundles.start_task_brief, ("task_id",)),
    "hygiene": (bundles.hygiene, ("project_id",)),
    "blast_radius": (bundles.blast_radius, ("task_id",)),
    "recurring_issues": (bundles.recurring_issues, ("scope",)),
}


def list_recipes() -> dict[str, list[str]]:
    return {name: list(params) for name, (_, params) in RECIPES.items()}


def run_recipe(
    core: GraphCore, principal: Principal, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    if name not in RECIPES:
        raise GraphError(
            ErrorCode.NOT_FOUND, f"Unknown recipe {name!r}", hint=f"Recipes: {', '.join(RECIPES)}"
        )
    fn, params = RECIPES[name]
    missing = [p for p in params if p not in args]
    if missing:
        raise GraphError(
            ErrorCode.ONTOLOGY_VIOLATION,
            f"Recipe {name} needs {', '.join(missing)}",
            hint=f"Pass {', '.join(f'{p}=<value>' for p in missing)}.",
        )
    extra = {k: v for k, v in args.items() if k not in params}
    return fn(bundles.Reader(core, principal), *(args[p] for p in params), **extra)
