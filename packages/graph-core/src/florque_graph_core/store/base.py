"""Graph store interface (spec 5.6).

The engine only talks to a database through these primitives. ``read`` and
``write`` each run a callable inside one transaction; ``write`` commits when the
callable returns and rolls back when it raises.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar

if TYPE_CHECKING:
    from florque_graph_core.integrity import IntegrityCheck
    from florque_graph_core.ontology.model import OntologyModel

T = TypeVar("T")
Direction = Literal["out", "in", "both"]


class UniqueViolation(Exception):
    """A uniqueness constraint fired. ``what`` is one of id, dedupe, idempotency."""

    def __init__(self, what: str, message: str = "") -> None:
        super().__init__(message or what)
        self.what = what


@dataclass(frozen=True)
class Edge:
    rel: str
    src: str
    dst: str
    props: Mapping[str, Any] = field(default_factory=dict)


class StoreTx(Protocol):
    def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    def get_nodes(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]: ...

    def find_nodes(
        self,
        label: str,
        where: Mapping[str, Any] | None = None,
        project_id: str | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def create_node(self, labels: Sequence[str], props: Mapping[str, Any]) -> None: ...

    def update_node(
        self,
        node_id: str,
        set_props: Mapping[str, Any],
        remove: Sequence[str] = (),
        expected_version: int | None = None,
    ) -> bool: ...

    def create_edge(
        self, rel: str, src: str, dst: str, props: Mapping[str, Any] | None = None
    ) -> None: ...

    def delete_edge(self, rel: str, src: str, dst: str) -> int: ...

    def edges(
        self, node_id: str, direction: Direction = "both", rels: Sequence[str] | None = None
    ) -> list[Edge]: ...

    def search(
        self, project_id: str, terms: Sequence[str], label: str | None, limit: int
    ) -> list[dict[str, Any]]: ...

    def get_idempotency(self, key: str) -> dict[str, Any] | None: ...

    def put_idempotency(self, key: str, record: Mapping[str, Any]) -> None: ...

    def append_change(self, entry: Mapping[str, Any]) -> int:
        """Store a change-log entry and return its monotonic sequence number."""
        ...

    def changes(self, project_id: str, since: int | None, limit: int) -> list[dict[str, Any]]: ...

    def run_integrity(
        self, checks: Sequence[IntegrityCheck], project_id: str
    ) -> list[dict[str, Any]] | None:
        """Run checks natively over a whole project; return None to use the generic evaluator."""
        ...


class GraphStore(Protocol):
    name: str

    def ensure_schema(self, model: OntologyModel) -> None: ...

    def read(self, fn: Callable[[StoreTx], T]) -> T: ...

    def write(self, fn: Callable[[StoreTx], T]) -> T: ...

    def health(self) -> dict[str, Any]: ...

    def close(self) -> None: ...
