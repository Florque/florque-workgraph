"""Neo4j graph store (spec 5.7). Labels: class, Node and mixin names; relationship types: uppercase slot names."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from neo4j import GraphDatabase, ManagedTransaction
from neo4j.exceptions import ConstraintError

from florque_graph_core.integrity import IntegrityCheck
from florque_graph_core.ontology.model import OntologyModel
from florque_graph_core.store import queries as q
from florque_graph_core.store.base import Direction, Edge, UniqueViolation

T = TypeVar("T")


def _clean(props: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            continue
        out[k] = json.dumps(v) if isinstance(v, dict) else v
    return out


def _unique_what(err: ConstraintError) -> str:
    msg = str(err)
    if "dedupe_key" in msg:
        return "dedupe"
    if "_Idempotency" in msg:
        return "idempotency"
    return "id"


class Neo4jStoreTx:
    def __init__(self, tx: ManagedTransaction) -> None:
        self.tx = tx

    def _run(self, query: str, **params: Any) -> list[Any]:
        try:
            return list(self.tx.run(query, **params))
        except ConstraintError as e:
            raise UniqueViolation(_unique_what(e), str(e)) from e

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        rows = self._run(q.GET_NODE, id=node_id)
        return dict(rows[0]["n"]) if rows else None

    def get_nodes(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        return {r["n"]["id"]: dict(r["n"]) for r in self._run(q.GET_NODES, ids=list(ids))}

    def find_nodes(
        self,
        label: str,
        where: Mapping[str, Any] | None = None,
        project_id: str | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        keys = list((where or {}).keys())
        query = q.find_nodes(
            label, keys, project_id is not None, include_archived, limit is not None
        )
        params = {f"w{i}": (where or {})[k] for i, k in enumerate(keys)}
        rows = self._run(query, project_id=project_id, limit=limit, **params)
        return [dict(r["n"]) for r in rows]

    def create_node(self, labels: Sequence[str], props: Mapping[str, Any]) -> None:
        self._run(q.create_node(labels), props=_clean(props))

    def update_node(
        self,
        node_id: str,
        set_props: Mapping[str, Any],
        remove: Sequence[str] = (),
        expected_version: int | None = None,
    ) -> bool:
        nulls = [k for k, v in set_props.items() if v is None]
        rows = self._run(
            q.update_node([*remove, *nulls]), id=node_id, ev=expected_version, set=_clean(set_props)
        )
        return bool(rows and rows[0]["c"])

    def create_edge(
        self, rel: str, src: str, dst: str, props: Mapping[str, Any] | None = None
    ) -> None:
        self._run(q.create_edge(rel), src=src, dst=dst, props=_clean(props or {}))

    def delete_edge(self, rel: str, src: str, dst: str) -> int:
        rows = self._run(q.delete_edge(rel), src=src, dst=dst)
        return int(rows[0]["c"]) if rows else 0

    def edges(
        self, node_id: str, direction: Direction = "both", rels: Sequence[str] | None = None
    ) -> list[Edge]:
        rows = self._run(q.edges(direction, rels), id=node_id)
        return [Edge(r["rel"], r["src"], r["dst"], dict(r["props"])) for r in rows]

    def search(
        self, project_id: str, terms: Sequence[str], label: str | None, limit: int
    ) -> list[dict[str, Any]]:
        rows = self._run(q.search(label), project_id=project_id, terms=list(terms), limit=limit * 5)
        return [dict(r["n"]) for r in rows]

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        rows = self._run(q.GET_IDEMPOTENCY, key=key)
        if not rows:
            return None
        rec = dict(rows[0]["i"])
        rec["result"] = json.loads(rec.get("result") or "null")
        return rec

    def put_idempotency(self, key: str, record: Mapping[str, Any]) -> None:
        props = {**record, "key": key, "result": json.dumps(record.get("result"))}
        self._run(q.PUT_IDEMPOTENCY, props=_clean(props))

    def append_change(self, entry: Mapping[str, Any]) -> int:
        props = {**entry, "patch": json.dumps(entry.get("patch"))}
        rows = self._run(q.APPEND_CHANGE, props=_clean(props))
        return int(rows[0]["seq"])

    def changes(self, project_id: str, since: int | None, limit: int) -> list[dict[str, Any]]:
        rows = self._run(q.CHANGES, project_id=project_id, since=since, limit=limit)
        out = []
        for r in rows:
            c = dict(r["c"])
            c["patch"] = json.loads(c.get("patch") or "null")
            out.append(c)
        return out

    def run_integrity(
        self, checks: Sequence[IntegrityCheck], project_id: str
    ) -> list[dict[str, Any]] | None:
        rows: list[dict[str, Any]] = []
        for chk in checks:
            rows.extend(dict(r) for r in self._run(q.integrity_query(chk), project_id=project_id))
        return rows


class Neo4jStore:
    name = "neo4j"

    def __init__(self, uri: str, user: str, password: str, database: str | None = None) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def ensure_schema(self, model: OntologyModel) -> None:
        with self._driver.session(database=self._database) as s:
            for stmt in q.constraint_statements(model):
                s.run(stmt).consume()

    def read(self, fn: Callable[[Neo4jStoreTx], T]) -> T:
        with self._driver.session(database=self._database) as s:
            return s.execute_read(lambda tx: fn(Neo4jStoreTx(tx)))

    def write(self, fn: Callable[[Neo4jStoreTx], T]) -> T:
        with self._driver.session(database=self._database) as s:
            try:
                return s.execute_write(lambda tx: fn(Neo4jStoreTx(tx)))
            except ConstraintError as e:  # raised at commit
                raise UniqueViolation(_unique_what(e), str(e)) from e

    def health(self) -> dict[str, Any]:
        try:
            with self._driver.session(database=self._database) as s:
                s.run(q.HEALTH).consume()
            return {"ok": True, "store": self.name}
        except Exception as e:  # pragma: no cover - depends on infrastructure
            return {"ok": False, "store": self.name, "error": str(e)}

    def close(self) -> None:
        self._driver.close()
