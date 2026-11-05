"""In-process graph store for tests and quick local use.

With ``path`` set, the state is loaded from and saved to a JSON file after each
committed write: handy for single-user local mode without a database, but not a
substitute for Neo4j (no concurrency across processes).

It enforces the same uniqueness constraints as the Neo4j schema (unique id;
unique (project_id, dedupe_key) per class label; unique idempotency key), and
serializes writes with a lock, rolling back on error.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

from florque_graph_core.integrity import IntegrityCheck
from florque_graph_core.ontology.model import OntologyModel
from florque_graph_core.store.base import Direction, Edge, UniqueViolation

T = TypeVar("T")


class _State:
    def __init__(self) -> None:
        self.nodes: dict[str, tuple[frozenset[str], dict[str, Any]]] = {}
        self.edges: list[Edge] = []
        self.idempotency: dict[str, dict[str, Any]] = {}
        self.changes: list[dict[str, Any]] = []

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": {k: {"labels": sorted(lbl), "props": p} for k, (lbl, p) in self.nodes.items()},
            "edges": [
                {"rel": e.rel, "src": e.src, "dst": e.dst, "props": dict(e.props)}
                for e in self.edges
            ],
            "idempotency": self.idempotency,
            "changes": self.changes,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> _State:
        s = cls()
        s.nodes = {
            k: (frozenset(v["labels"]), v["props"]) for k, v in data.get("nodes", {}).items()
        }
        s.edges = [
            Edge(e["rel"], e["src"], e["dst"], e.get("props") or {}) for e in data.get("edges", [])
        ]
        s.idempotency = data.get("idempotency", {})
        s.changes = data.get("changes", [])
        return s


class MemoryStoreTx:
    def __init__(self, state: _State, store: MemoryStore) -> None:
        self.s = state
        self.a = store

    def _out(self, labels: frozenset[str], props: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(props)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        n = self.s.nodes.get(node_id)
        return self._out(*n) if n else None

    def get_nodes(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        return {i: self._out(*self.s.nodes[i]) for i in ids if i in self.s.nodes}

    def find_nodes(
        self,
        label: str,
        where: Mapping[str, Any] | None = None,
        project_id: str | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        out = []
        for labels, p in self.s.nodes.values():
            if label not in labels:
                continue
            if project_id is not None and p.get("project_id") != project_id:
                continue
            if not include_archived and p.get("status") == "archived":
                continue
            if where and any(p.get(k) != v for k, v in where.items()):
                continue
            out.append(self._out(labels, p))
        out.sort(key=lambda n: (n.get("created_at") or "", n["id"]))
        return out[:limit] if limit else out

    def create_node(self, labels: Sequence[str], props: Mapping[str, Any]) -> None:
        nid = props["id"]
        if nid in self.s.nodes:
            raise UniqueViolation("id", f"node {nid} exists")
        dk = props.get("dedupe_key")
        if dk is not None:
            for lbl in labels:
                if lbl not in self.a.dedupe_labels:
                    continue
                global_scope = lbl in self.a.global_labels
                for other_labels, op in self.s.nodes.values():
                    if (
                        lbl in other_labels
                        and op.get("dedupe_key") == dk
                        and (global_scope or op.get("project_id") == props.get("project_id"))
                    ):
                        raise UniqueViolation("dedupe", f"dedupe_key {dk} exists for {lbl}")
        self.s.nodes[nid] = (frozenset(labels), {k: v for k, v in props.items() if v is not None})

    def update_node(
        self,
        node_id: str,
        set_props: Mapping[str, Any],
        remove: Sequence[str] = (),
        expected_version: int | None = None,
    ) -> bool:
        n = self.s.nodes.get(node_id)
        if n is None:
            return False
        labels, p = n
        if expected_version is not None and p.get("version") != expected_version:
            return False
        dk = set_props.get("dedupe_key")
        if dk is not None and dk != p.get("dedupe_key"):
            for lbl in labels & self.a.dedupe_labels:
                for oid, (ol, op) in self.s.nodes.items():
                    if (
                        oid != node_id
                        and lbl in ol
                        and op.get("dedupe_key") == dk
                        and (
                            lbl in self.a.global_labels
                            or op.get("project_id") == p.get("project_id")
                        )
                    ):
                        raise UniqueViolation("dedupe", f"dedupe_key {dk} exists for {lbl}")
        for k, v in set_props.items():
            if v is None:
                p.pop(k, None)
            else:
                p[k] = copy.deepcopy(v)
        for k in remove:
            p.pop(k, None)
        return True

    def create_edge(
        self, rel: str, src: str, dst: str, props: Mapping[str, Any] | None = None
    ) -> None:
        self.delete_edge(rel, src, dst)
        self.s.edges.append(Edge(rel, src, dst, dict(props or {})))

    def delete_edge(self, rel: str, src: str, dst: str) -> int:
        before = len(self.s.edges)
        self.s.edges = [
            e for e in self.s.edges if not (e.rel == rel and e.src == src and e.dst == dst)
        ]
        return before - len(self.s.edges)

    def edges(
        self, node_id: str, direction: Direction = "both", rels: Sequence[str] | None = None
    ) -> list[Edge]:
        out = []
        for e in self.s.edges:
            if rels is not None and e.rel not in rels:
                continue
            if (direction in ("out", "both") and e.src == node_id) or (
                direction in ("in", "both") and e.dst == node_id
            ):
                out.append(Edge(e.rel, e.src, e.dst, dict(e.props)))
        return out

    def search(
        self, project_id: str, terms: Sequence[str], label: str | None, limit: int
    ) -> list[dict[str, Any]]:
        out = []
        for labels, p in self.s.nodes.values():
            if p.get("project_id") != project_id or (label and label not in labels):
                continue
            hay = " ".join(
                [p.get("title", ""), p.get("summary", ""), *p.get("aliases", [])]
            ).lower()
            if any(t in hay for t in terms):
                out.append(self._out(labels, p))
        return out[: limit * 5]

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        r = self.s.idempotency.get(key)
        return copy.deepcopy(r) if r else None

    def put_idempotency(self, key: str, record: Mapping[str, Any]) -> None:
        if key in self.s.idempotency:
            raise UniqueViolation("idempotency", key)
        self.s.idempotency[key] = dict(record)

    def append_change(self, entry: Mapping[str, Any]) -> int:
        seq = len(self.s.changes) + 1
        self.s.changes.append({**entry, "seq": seq})
        return seq

    def changes(self, project_id: str, since: int | None, limit: int) -> list[dict[str, Any]]:
        rows = [
            c
            for c in self.s.changes
            if c.get("project_id") == project_id and (since is None or c["seq"] > since)
        ]
        return copy.deepcopy(rows[:limit])

    def run_integrity(
        self, checks: Sequence[IntegrityCheck], project_id: str
    ) -> list[dict[str, Any]] | None:
        return None


class MemoryStore:
    name = "memory"

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else None
        self._state = _State()
        if self.path and self.path.exists():
            self._state = _State.from_json(json.loads(self.path.read_text()))
        self._lock = threading.RLock()
        self.dedupe_labels: frozenset[str] = frozenset()
        self.global_labels: frozenset[str] = frozenset()

    def ensure_schema(self, model: OntologyModel) -> None:
        self.dedupe_labels = frozenset(c.name for c in model.concrete())
        self.global_labels = frozenset(c.name for c in model.concrete() if c.is_global or c.root)

    def read(self, fn: Callable[[MemoryStoreTx], T]) -> T:
        with self._lock:
            return fn(MemoryStoreTx(self._state, self))

    def write(self, fn: Callable[[MemoryStoreTx], T]) -> T:
        with self._lock:
            snapshot = copy.deepcopy(self._state)
            try:
                result = fn(MemoryStoreTx(self._state, self))
            except BaseException:
                self._state = snapshot
                raise
            if self.path:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._state.to_json()))
                tmp.replace(self.path)
            return result

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "store": self.name,
            "nodes": len(self._state.nodes),
            "path": str(self.path or ""),
        }

    def close(self) -> None:
        pass
