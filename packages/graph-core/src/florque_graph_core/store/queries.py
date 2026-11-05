"""The only Cypher in graph-core (spec 5.6). Every query is parameterized.

Labels, relationship types and property keys cannot be parameters in Cypher, so
they are interpolated only after passing ``ident`` (they come from the validated
ontology, never from user input).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from florque_graph_core.integrity import IntegrityCheck
from florque_graph_core.ontology.model import OntologyModel

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe identifier: {name!r}")
    return name


def labels(names: Iterable[str]) -> str:
    return "".join(f":{ident(n)}" for n in names)


# ---------------------------------------------------------------- schema


def constraint_statements(model: OntologyModel) -> list[str]:
    out = [
        "CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT idempotency_key_unique IF NOT EXISTS FOR (n:_Idempotency) REQUIRE n.key IS UNIQUE",
    ]
    for c in sorted(model.concrete(), key=lambda c: c.name):
        name = ident(c.name)
        if c.is_global or c.root:
            out.append(
                f"CREATE CONSTRAINT {name.lower()}_dedupe_unique IF NOT EXISTS "
                f"FOR (n:{name}) REQUIRE n.dedupe_key IS UNIQUE"
            )
        else:
            out.append(
                f"CREATE CONSTRAINT {name.lower()}_dedupe_unique IF NOT EXISTS "
                f"FOR (n:{name}) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE"
            )
    for prop in ("project_id", "status", "series_code", "observed_at"):
        out.append(f"CREATE INDEX node_{prop} IF NOT EXISTS FOR (n:Node) ON (n.{prop})")
    out.append(
        "CREATE INDEX changelog_project_seq IF NOT EXISTS FOR (c:_ChangeLog) ON (c.project_id, c.seq)"
    )
    out.append(
        "CREATE CONSTRAINT sequence_name_unique IF NOT EXISTS FOR (s:_Sequence) REQUIRE s.name IS UNIQUE"
    )
    return out


# ---------------------------------------------------------------- nodes

GET_NODE = "MATCH (n:Node {id: $id}) RETURN properties(n) AS n"
GET_NODES = "MATCH (n:Node) WHERE n.id IN $ids RETURN properties(n) AS n"


def find_nodes(
    label: str, keys: Sequence[str], has_project: bool, include_archived: bool, limit: bool
) -> str:
    conds = [f"n.{ident(k)} = $w{i}" for i, k in enumerate(keys)]
    if has_project:
        conds.append("n.project_id = $project_id")
    if not include_archived:
        conds.append("coalesce(n.status, '') <> 'archived'")
    where = f" WHERE {' AND '.join(conds)}" if conds else ""
    lim = " LIMIT $limit" if limit else ""
    return f"MATCH (n:{ident(label)}){where} RETURN properties(n) AS n ORDER BY n.created_at, n.id{lim}"


def create_node(node_labels: Sequence[str]) -> str:
    return f"CREATE (n{labels(node_labels)}) SET n = $props"


def update_node(remove: Sequence[str]) -> str:
    rm = "".join(f" REMOVE n.{ident(k)}" for k in remove)
    return (
        "MATCH (n:Node {id: $id}) WHERE $ev IS NULL OR n.version = $ev "
        f"SET n += $set{rm} RETURN count(n) AS c"
    )


# ---------------------------------------------------------------- edges


def create_edge(rel: str) -> str:
    r = ident(rel)
    return (
        f"MATCH (a:Node {{id: $src}}), (b:Node {{id: $dst}}) MERGE (a)-[r:{r}]->(b) SET r = $props"
    )


def delete_edge(rel: str) -> str:
    return f"MATCH (:Node {{id: $src}})-[r:{ident(rel)}]->(:Node {{id: $dst}}) DELETE r RETURN count(r) AS c"


def edges(direction: str, rels: Sequence[str] | None) -> str:
    rel = ""
    if rels:
        rel = ":" + "|".join(ident(r) for r in rels)
    pattern = {
        "out": f"(n)-[r{rel}]->(m)",
        "in": f"(n)<-[r{rel}]-(m)",
        "both": f"(n)-[r{rel}]-(m)",
    }[direction]
    return (
        f"MATCH (n:Node {{id: $id}}) MATCH {pattern} WHERE m:Node "
        "RETURN type(r) AS rel, startNode(r).id AS src, endNode(r).id AS dst, properties(r) AS props"
    )


# ---------------------------------------------------------------- search


def search(label: str | None) -> str:
    lbl = f":{ident(label)}" if label else ":Node"
    return (
        f"MATCH (n{lbl}) WHERE n.project_id = $project_id AND any(t IN $terms WHERE "
        "toLower(n.title) CONTAINS t OR toLower(coalesce(n.summary, '')) CONTAINS t "
        "OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS t)) "
        "RETURN properties(n) AS n LIMIT $limit"
    )


# ---------------------------------------------------------------- infrastructure

GET_IDEMPOTENCY = "MATCH (i:_Idempotency {key: $key}) RETURN properties(i) AS i"
PUT_IDEMPOTENCY = "CREATE (i:_Idempotency) SET i = $props"
APPEND_CHANGE = (
    "MERGE (s:_Sequence {name: 'changelog'}) SET s.value = coalesce(s.value, 0) + 1 "
    "WITH s CREATE (c:_ChangeLog) SET c = $props, c.seq = s.value RETURN c.seq AS seq"
)
CHANGES = (
    "MATCH (c:_ChangeLog) WHERE c.project_id = $project_id AND ($since IS NULL OR c.seq > $since) "
    "RETURN properties(c) AS c ORDER BY c.seq LIMIT $limit"
)
HEALTH = "RETURN 1 AS ok"


# ---------------------------------------------------------------- integrity


def _allowed_expr(allowed: Sequence[tuple[str, str | None]]) -> str:
    parts = []
    for c, k in allowed:
        cond = f"p:{ident(c)}"
        if k:
            cond += f" AND p.kind = '{ident(k)}'"
        parts.append(f"({cond})")
    return " OR ".join(parts) or "false"


def integrity_query(chk: IntegrityCheck) -> str:
    live = "coalesce(n.status, '') <> 'archived'"
    head = f"'{ident(chk.name)}' AS `check`, n.id AS node_id"
    kind = f" AND n.kind = '{ident(chk.node_kind)}'" if chk.node_kind else ""
    if chk.kind == "orphan":
        return (
            f"MATCH (n:{ident(chk.cls or 'Node')}) WHERE n.project_id = $project_id AND {live} "
            f"AND NOT (n)-[:PART_OF]->(:Node) RETURN {head}, 'no parent' AS detail"
        )
    if chk.kind == "multiple_parents":
        return (
            f"MATCH (n:Node)-[r:PART_OF]->(:Node) WHERE n.project_id = $project_id AND {live} "
            f"WITH n, count(r) AS c WHERE c > 1 RETURN {head}, toString(c) + ' parents' AS detail"
        )
    if chk.kind == "parent_kind":
        return (
            f"MATCH (n:{ident(chk.cls or 'Node')})-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id "
            f"AND {live}{kind} AND NOT ({_allowed_expr(chk.allowed)}) "
            f"RETURN {head}, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail"
        )
    if chk.kind == "required_edge":
        return (
            f"MATCH (n:{ident(chk.cls or 'Node')}) WHERE n.project_id = $project_id AND {live}{kind} "
            f"AND NOT (n)-[:{ident(chk.rel or '')}]->(:Node) RETURN {head}, 'missing {chk.rel}' AS detail"
        )
    if chk.kind == "no_membership":
        return (
            f"MATCH (n:{ident(chk.cls or 'Node')})-[:{ident(chk.rel or '')}]->(:Node) WITH collect(DISTINCT n.id) AS members "
            f"MATCH (n:{ident(chk.cls or 'Node')}) WHERE {live} AND NOT n.id IN members "
            f"AND (n)-[]-(:Node {{project_id: $project_id}}) RETURN {head}, 'no membership' AS detail"
        )
    if chk.kind == "cross_project":
        return (
            "MATCH (n:Node)-[r]->(m:Node) WHERE n.project_id = $project_id "
            "AND n.project_id IS NOT NULL AND m.project_id IS NOT NULL AND n.project_id <> m.project_id "
            f"RETURN {head}, type(r) + ' ' + n.id + '->' + m.id AS detail"
        )
    raise ValueError(f"unknown check kind {chk.kind}")
