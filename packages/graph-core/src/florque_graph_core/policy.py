"""Host-injected authorization and lifecycle policy.

graph-core enforces; the host (workgraph) decides. Field ownership comes from
`owner` annotations in the ontology; the policy maps roles to the owner classes
they may write (spec 4.7, 6.5).
"""

from __future__ import annotations

from typing import Any, Protocol

STATUS_ORDER = {"proposed": 0, "active": 1, "done": 2, "archived": 3}


class Policy(Protocol):
    def can_read(self, role: str | None) -> bool: ...

    def can_create(self, role: str | None, cls: str, kind: str | None) -> bool: ...

    def writable_owners(self, role: str | None) -> set[str]: ...

    def can_link(self, role: str | None, edge_slot: str) -> bool: ...

    def can_structure(self, role: str | None) -> bool:
        """Archive, move and merge."""
        ...

    def initial_status(
        self, role: str | None, is_agent: bool, cls: str, kind: str | None, requested: str | None
    ) -> str: ...

    def check_transition(
        self, role: str | None, node: dict[str, Any], new_status: str
    ) -> str | None:
        """Return a reason string if the status change is not allowed."""
        ...


class DefaultPolicy:
    """Conservative default: admin and contributor write human fields, viewer reads."""

    WRITERS = {"admin", "contributor"}

    def can_read(self, role: str | None) -> bool:
        return role is not None

    def can_create(self, role: str | None, cls: str, kind: str | None) -> bool:
        return role in self.WRITERS

    def writable_owners(self, role: str | None) -> set[str]:
        return {"human"} if role in self.WRITERS else set()

    def can_link(self, role: str | None, edge_slot: str) -> bool:
        return role in self.WRITERS

    def can_structure(self, role: str | None) -> bool:
        return role in self.WRITERS

    def initial_status(
        self, role: str | None, is_agent: bool, cls: str, kind: str | None, requested: str | None
    ) -> str:
        return requested or "proposed"

    def check_transition(
        self, role: str | None, node: dict[str, Any], new_status: str
    ) -> str | None:
        return None
