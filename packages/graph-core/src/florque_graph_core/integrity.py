"""Integrity checks derived from the ontology.

Checks are data. The Neo4j store renders them to Cypher (and the generator
writes integrity_checks.cypher); every store can also run them through the
generic evaluator below, which the engine uses for touched-node checks inside
the write transaction.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from florque_graph_core.errors import ErrorCode
from florque_graph_core.ontology.model import OntologyModel
from florque_graph_core.store.base import StoreTx

PART_OF = "PART_OF"


@dataclass(frozen=True)
class IntegrityCheck:
    name: str
    kind: str  # orphan | multiple_parents | parent_kind | required_edge | cross_project | no_membership
    cls: str | None = None
    node_kind: str | None = None
    rel: str | None = None
    allowed: tuple[tuple[str, str | None], ...] = ()
    description: str = ""

    @property
    def error_code(self) -> ErrorCode:
        return {
            "orphan": ErrorCode.PARENT_RULE,
            "multiple_parents": ErrorCode.PARENT_RULE,
            "parent_kind": ErrorCode.PARENT_RULE,
            "required_edge": ErrorCode.REQUIRED_EDGE,
            "cross_project": ErrorCode.SCOPE_VIOLATION,
            "no_membership": ErrorCode.REQUIRED_EDGE,
        }[self.kind]


def build_checks(model: OntologyModel) -> list[IntegrityCheck]:
    checks: list[IntegrityCheck] = [
        IntegrityCheck(
            "multiple_parents", "multiple_parents", description="Node with more than one parent"
        ),
        IntegrityCheck(
            "cross_project_edge",
            "cross_project",
            description="Edge between nodes of different projects (Actor targets exempt)",
        ),
    ]
    for c in model.concrete():
        if c.root:
            continue
        if c.is_global:
            if "member_of" in c.edges:
                checks.append(
                    IntegrityCheck(
                        f"{c.name.lower()}_without_membership",
                        "no_membership",
                        cls=c.name,
                        rel=c.edges["member_of"].rel_type,
                        description=f"{c.name} with no member_of edge",
                    )
                )
        else:
            checks.append(
                IntegrityCheck(
                    f"{c.name.lower()}_orphan",
                    "orphan",
                    cls=c.name,
                    description=f"{c.name} without a parent",
                )
            )
        kinds: list[str | None] = list(c.kinds) if c.kinds else [None]
        for kind in kinds:
            allowed = c.parent_rules(kind)
            if allowed:
                suffix = f"_{kind}" if kind else ""
                checks.append(
                    IntegrityCheck(
                        f"{c.name.lower()}{suffix}_parent_kind",
                        "parent_kind",
                        cls=c.name,
                        node_kind=kind,
                        allowed=allowed,
                        description=f"{c.name}{':' + kind if kind else ''} under a parent not in {_fmt(allowed)}",
                    )
                )
            for req in c.required_edges(kind):
                checks.append(
                    IntegrityCheck(
                        f"{c.name.lower()}_{kind}_without_{req}",
                        "required_edge",
                        cls=c.name,
                        node_kind=kind,
                        rel=c.edges[req].rel_type,
                        description=f"Live {c.name}:{kind} without a {req} edge",
                    )
                )
    return checks


def _fmt(allowed: Iterable[tuple[str, str | None]]) -> str:
    return ", ".join(f"{c}:{k}" if k else c for c, k in allowed)


def _parent_ok(parent: dict[str, Any] | None, allowed: Sequence[tuple[str, str | None]]) -> bool:
    if parent is None:
        return True  # orphan check reports it
    return any(
        parent.get("class") == c and (k is None or parent.get("kind") == k) for c, k in allowed
    )


def evaluate(
    tx: StoreTx,
    model: OntologyModel,
    checks: Sequence[IntegrityCheck],
    nodes: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generic evaluator over graph-store primitives, for a given set of nodes."""
    rows: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("status") == "archived":
            continue
        out_edges = tx.edges(n["id"], "out")
        parents = [e for e in out_edges if e.rel == PART_OF]
        parent = tx.get_node(parents[0].dst) if parents else None
        for chk in checks:
            if chk.cls and n.get("class") != chk.cls:
                continue
            if chk.node_kind and n.get("kind") != chk.node_kind:
                continue
            bad = False
            detail = ""
            if chk.kind == "orphan":
                bad = not parents
            elif chk.kind == "multiple_parents":
                bad = len(parents) > 1
            elif chk.kind == "parent_kind":
                bad = parents != [] and not _parent_ok(parent, chk.allowed)
                detail = (
                    f"parent={parent.get('class')}:{parent.get('kind')}" if bad and parent else ""
                )
            elif chk.kind in ("required_edge", "no_membership"):
                bad = not any(e.rel == chk.rel for e in out_edges)
            elif chk.kind == "cross_project":
                for e in tx.edges(n["id"], "both"):
                    other_id = e.dst if e.src == n["id"] else e.src
                    other = tx.get_node(other_id)
                    if other is None:
                        continue
                    cs, co = (
                        model.classes.get(n.get("class", "")),
                        model.classes.get(other.get("class", "")),
                    )
                    if (cs and cs.is_global) or (co and co.is_global):
                        continue
                    if other.get("project_id") != n.get("project_id"):
                        bad, detail = True, f"{e.rel} {e.src}->{e.dst}"
                        break
            if bad:
                rows.append(
                    {"check": chk.name, "node_id": n["id"], "detail": detail or chk.description}
                )
    return rows
