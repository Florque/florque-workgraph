"""Work-graph policies: role to capability map, lifecycle rules (spec 4.7, 6.5, 7).

Merge and dedupe behaviour per class are declared in the ontology (`merge`,
`dedupe_scope`, `natural_key` annotations); this module decides who may do what.
"""

from __future__ import annotations

from typing import Any

# Which field owner classes each role may write (spec 4.7, resolution 7).
ROLE_OWNERS: dict[str, set[str]] = {
    "admin": {"human"},
    "contributor": {"human"},
    "viewer": set(),
    "hub": {"evaluator", "hub"},
}

# What the hub may create (spec 6.5): Signals of these kinds, never structure.
HUB_SIGNAL_KINDS = {"metric", "feedback", "incident", "update"}
HUB_EDGES = {"about"}

WRITERS = {"admin", "contributor"}


class WorkgraphPolicy:
    def can_read(self, role: str | None) -> bool:
        return role in ROLE_OWNERS

    def can_create(self, role: str | None, cls: str, kind: str | None) -> bool:
        if role in WRITERS:
            return cls != "Project" or role == "admin"
        if role == "hub":
            return cls == "Signal" and kind in HUB_SIGNAL_KINDS
        return False

    def writable_owners(self, role: str | None) -> set[str]:
        return ROLE_OWNERS.get(role or "", set())

    def can_link(self, role: str | None, edge_slot: str) -> bool:
        if role in WRITERS:
            return True
        return role == "hub" and edge_slot in HUB_EDGES

    def can_structure(self, role: str | None) -> bool:
        return role in WRITERS

    def initial_status(
        self, role: str | None, is_agent: bool, cls: str, kind: str | None, requested: str | None
    ) -> str:
        if role == "contributor" and is_agent:
            return "proposed"  # agent writes start as proposed; an admin accepts them
        if role == "hub":
            return requested or "active"
        return requested or "proposed"

    def check_transition(
        self, role: str | None, node: dict[str, Any], new_status: str
    ) -> str | None:
        current = node.get("status", "proposed")
        if current == "proposed" and new_status != "proposed" and role != "admin":
            return "Only a project admin accepts proposals (proposed -> active/done)."
        if current == "done" and new_status in ("proposed", "active") and role != "admin":
            return "Only a project admin reopens finished work."
        return None
