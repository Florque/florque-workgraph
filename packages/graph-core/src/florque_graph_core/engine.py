"""GraphCore: CRUD against a graph database, validated against an injected ontology (spec 5).

Every write runs the validation pipeline inside one graph-store transaction:

1. class and kind  2. fields  3. rules  4. edge typing  5. parent rules
6. project isolation  7. field ownership  8. duplicates
9. write + idempotency record + change-log entry  10. touched-node integrity checks

Public methods raise GraphError; wrap them with ``errors.envelope`` for the
{ok, data} response shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from florque_graph_core.dedupe import dedupe_key, normalize_title, similarity
from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.hooks import Hook, WriteContext
from florque_graph_core.integrity import PART_OF, build_checks, evaluate
from florque_graph_core.ontology.model import SYSTEM_FIELDS, ClassSpec, EdgeSpec, OntologyModel
from florque_graph_core.policy import STATUS_ORDER, DefaultPolicy, Policy
from florque_graph_core.principal import WILDCARD, Principal
from florque_graph_core.store.base import GraphStore, StoreTx, UniqueViolation
from florque_graph_core.validation.values import (
    check_kind,
    check_required,
    check_rules,
    format_datetime,
    resolve_class,
    validate_fields,
)

ROLE_RANK = {"viewer": 0, "hub": 1, "contributor": 2, "admin": 3}


@dataclass(frozen=True)
class EdgeRequest:
    slot: str
    to: str
    props: Mapping[str, Any]


def _edge_requests(edges: Iterable[Mapping[str, Any]] | None) -> list[EdgeRequest]:
    out = []
    for e in edges or ():
        etype = e.get("type") or e.get("edge")
        if not etype or not e.get("to"):
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Malformed edge {dict(e)!r}",
                hint='Edges look like {"type": "serves", "to": "<node id>"}.',
            )
        out.append(EdgeRequest(str(etype), str(e["to"]), dict(e.get("props") or {})))
    return out


def _strip(node: Mapping[str, Any]) -> dict[str, Any]:
    """Public view of a stored node."""
    return {k: v for k, v in node.items() if k not in ("dedupe_key", "archived_dedupe_key")}


class GraphCore:
    def __init__(
        self,
        ontology: OntologyModel,
        store: GraphStore,
        policy: Policy | None = None,
        hooks: Sequence[Hook] = (),
        *,
        similarity_threshold: float = 90.0,
        clock: Callable[[], datetime] | None = None,
        ensure_schema: bool = True,
    ) -> None:
        self.model = ontology
        self.store = store
        self.policy: Policy = policy or DefaultPolicy()
        self.hooks: list[Hook] = list(hooks)
        self.similarity_threshold = similarity_threshold
        self.clock = clock or (lambda: datetime.now(UTC))
        self.checks = build_checks(ontology)
        if ensure_schema:
            store.ensure_schema(ontology)

    # ------------------------------------------------------------------ helpers

    def register_hook(self, hook: Hook) -> None:
        self.hooks.append(hook)

    def _now(self) -> str:
        return format_datetime(self.clock())

    @staticmethod
    def _new_id(cls: str) -> str:
        return f"{cls.lower()}_{uuid.uuid4().hex[:16]}"

    def _node(self, tx: StoreTx, node_id: str) -> dict[str, Any]:
        n = tx.get_node(node_id)
        if n is None:
            raise GraphError(
                ErrorCode.NOT_FOUND,
                f"Node {node_id!r} not found",
                hint="Search for the node first.",
            )
        return n

    def _spec_of(self, node: Mapping[str, Any]) -> ClassSpec:
        return resolve_class(self.model, node["class"])

    def _role(self, principal: Principal, project_id: str | None) -> str | None:
        if project_id is not None:
            return principal.role_in(project_id)
        wildcard = principal.roles.get(WILDCARD)
        if wildcard:
            return wildcard
        best = None
        for r in principal.roles.values():
            if best is None or ROLE_RANK.get(r, -1) > ROLE_RANK.get(best, -1):
                best = r
        return best

    def role(self, principal: Principal, project_id: str | None) -> str | None:
        """The principal's role in a project (or its best role, for global scope)."""
        return self._role(principal, project_id)

    def _role_for_node(self, principal: Principal, node: Mapping[str, Any]) -> str | None:
        return self._role(principal, node.get("project_id"))

    def _require_read(self, principal: Principal, node: Mapping[str, Any]) -> str | None:
        role = self._role_for_node(principal, node)
        if not self.policy.can_read(role):
            raise GraphError(
                ErrorCode.FORBIDDEN,
                f"No access to project {node.get('project_id')!r}",
                hint="Ask a project admin for membership.",
            )
        return role

    def _dedupe(
        self,
        spec: ClassSpec,
        kind: str | None,
        parent_id: str | None,
        project_id: str | None,
        title: str,
    ) -> str | None:
        if spec.dedupe_scope == "none":
            return None
        return dedupe_key(spec.name, kind, self._scope_key(spec, parent_id, project_id), title)

    def _scope_key(
        self, spec: ClassSpec, parent_id: str | None, project_id: str | None
    ) -> str | None:
        if spec.dedupe_scope == "global":
            return None
        if spec.dedupe_scope == "root":
            return project_id
        return parent_id

    def _parent_id(self, tx: StoreTx, node_id: str) -> str | None:
        parents = tx.edges(node_id, "out", [PART_OF])
        return parents[0].dst if parents else None

    def _log(
        self,
        tx: StoreTx,
        principal: Principal,
        op: str,
        node: Mapping[str, Any],
        patch: Any = None,
        origin: str | None = None,
    ) -> None:
        tx.append_change(
            {
                "id": uuid.uuid4().hex,
                "at": self._now(),
                "project_id": node.get("project_id"),
                "actor_id": principal.actor_id,
                "op": op,
                "node_id": node["id"],
                "class": node.get("class"),
                "origin": origin,
                "patch": patch,
            }
        )

    def _integrity(self, tx: StoreTx, node_ids: Iterable[str]) -> None:
        nodes = list(tx.get_nodes(list(dict.fromkeys(node_ids))).values())
        rows = evaluate(tx, self.model, self.checks, nodes)
        if rows:
            first = rows[0]
            chk = next(c for c in self.checks if c.name == first["check"])
            raise GraphError(
                chk.error_code,
                f"Integrity check {first['check']} failed for {first['node_id']}: {first['detail']}",
                hint="Fix the parent or edges so the graph stays consistent.",
                details={"violations": rows},
            )

    def _idem(self, principal: Principal, op: str, key: str | None) -> str | None:
        return f"{principal.actor_id}:{op}:{key}" if key else None

    def _run_write(
        self, fn: Callable[[StoreTx], dict[str, Any]], idem: str | None
    ) -> dict[str, Any]:
        def wrapped(tx: StoreTx) -> dict[str, Any]:
            if idem:
                rec = tx.get_idempotency(idem)
                if rec:
                    return {**rec["result"], "replayed": True}
            result = fn(tx)
            if idem:
                tx.put_idempotency(idem, {"created_at": self._now(), "result": result})
            return result

        try:
            return self.store.write(wrapped)
        except UniqueViolation as u:
            if u.what == "idempotency" and idem:
                rec = self.store.read(lambda tx: tx.get_idempotency(idem))
                if rec:
                    return {**rec["result"], "replayed": True}
            if u.what == "dedupe":
                raise GraphError(
                    ErrorCode.DUPLICATE_EXACT,
                    "A node with the same identity was created concurrently",
                    hint="Search and reuse the existing node.",
                ) from u
            raise

    # ------------------------------------------------------------------ permission helpers

    def _check_owners(
        self, spec: ClassSpec, fields: Iterable[str], role: str | None, creating: bool
    ) -> None:
        writable = self.policy.writable_owners(role)
        for f in fields:
            slot = spec.slots[f]
            if slot.owner == "system":
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION, f"Field {f!r} is managed by the engine"
                )
            if creating and slot.owner == "human":
                continue  # authoring a node the role may create includes its human fields
            if slot.owner not in writable:
                raise GraphError(
                    ErrorCode.OWNERSHIP,
                    f"Role {role!r} may not write {spec.name}.{f} (owner: {slot.owner})",
                    hint=f"Fields owned by {slot.owner} are written by "
                    + (
                        "the evaluator (hub)." if slot.owner == "evaluator" else "a project member."
                    ),
                    details={"field": f, "owner": slot.owner, "role": role},
                )

    # ------------------------------------------------------------------ structure checks

    def _check_parent(self, spec: ClassSpec, kind: str | None, parent: Mapping[str, Any]) -> None:
        allowed = spec.parent_rules(kind)
        label = f"{spec.name}:{kind}" if kind else spec.name
        options = " or ".join(f"{c}:{k}" if k else c for c, k in allowed) or "no parent"
        if parent.get("status") == "archived":
            raise GraphError(
                ErrorCode.PARENT_RULE,
                f"Parent {parent['id']} is archived",
                hint=f"Use a live {options}.",
            )
        if not any(
            parent.get("class") == c and (k is None or parent.get("kind") == k) for c, k in allowed
        ):
            got = (
                f"{parent.get('class')}:{parent.get('kind')}"
                if parent.get("kind")
                else parent.get("class")
            )
            raise GraphError(
                ErrorCode.PARENT_RULE,
                f"A {label} cannot be placed under {got}",
                hint=f"Pass parent_id of a {options}.",
                details={"allowed_parents": [f"{c}:{k}" if k else c for c, k in allowed]},
            )

    def _check_edges(
        self,
        tx: StoreTx,
        spec: ClassSpec,
        src_project: str | None,
        requests: Sequence[EdgeRequest],
        principal: Principal,
    ) -> list[tuple[EdgeSpec, dict[str, Any], dict[str, Any]]]:
        resolved: list[tuple[EdgeSpec, dict[str, Any], dict[str, Any]]] = []
        counts: dict[str, int] = {}
        for req in requests:
            slot = self.model.slot_for_rel(req.slot)
            if slot == "part_of":
                raise GraphError(
                    ErrorCode.PARENT_RULE,
                    "part_of is set through parent_id",
                    hint="Pass parent_id on create, or use move.",
                )
            if slot is None or slot not in spec.edges:
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"{spec.name} has no edge {req.slot!r}",
                    hint=f"Edges of {spec.name}: {', '.join(e for e in spec.edges if e != 'part_of')}",
                )
            es = spec.edges[slot]
            target = self._node(tx, req.to)
            if target.get("class") not in es.targets:
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"{slot} cannot point from {spec.name} to {target.get('class')}",
                    hint=f"{slot} targets: {', '.join(sorted(es.targets))}",
                )
            if target.get("status") == "archived":
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"Target {req.to} is archived",
                    hint="Link to a live node.",
                )
            tspec = self._spec_of(target)
            if not (spec.is_global or tspec.is_global) and target.get("project_id") != src_project:
                raise GraphError(
                    ErrorCode.SCOPE_VIOLATION,
                    f"{slot} would cross projects ({src_project} -> {target.get('project_id')})",
                    hint="Only edges to or from an Actor may cross projects.",
                )
            # permission is decided in the project of the non-global endpoint
            perm_project = target.get("project_id") if spec.is_global else src_project
            role = self._role(principal, perm_project)
            if not self.policy.can_link(role, slot):
                raise GraphError(
                    ErrorCode.FORBIDDEN,
                    f"Role {role!r} may not create {slot} edges",
                    hint="Ask a project member.",
                )
            if slot == "member_of" and role != "admin":
                raise GraphError(ErrorCode.FORBIDDEN, "Only a project admin manages membership")
            props: dict[str, Any] = {}
            for k, v in req.props.items():
                if k not in es.properties:
                    raise GraphError(
                        ErrorCode.ONTOLOGY_VIOLATION,
                        f"Edge {slot} has no property {k!r}",
                        hint=f"Allowed: {', '.join(es.properties) or 'none'}",
                    )
                gs = self.model.global_slots.get(k)
                if gs and gs.enum_values and v not in gs.enum_values:
                    raise GraphError(
                        ErrorCode.ONTOLOGY_VIOLATION,
                        f"Edge property {k}={v!r} invalid",
                        hint=f"Use one of {list(gs.enum_values)}",
                    )
                props[k] = v
            counts[slot] = counts.get(slot, 0) + 1
            if not es.multivalued and counts[slot] > 1:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{slot} takes a single target")
            resolved.append((es, target, props))
        return resolved

    def _check_duplicates(
        self,
        tx: StoreTx,
        spec: ClassSpec,
        kind: str | None,
        props: Mapping[str, Any],
        project_id: str | None,
        parent_id: str | None,
        dk: str | None,
        confirm_new: bool,
        exclude_id: str | None = None,
    ) -> None:
        pid = None if spec.is_global or spec.root else project_id
        if spec.natural_key and all(props.get(f) is not None for f in spec.natural_key):
            where = {f: props[f] for f in spec.natural_key}
            found = [n for n in tx.find_nodes(spec.name, where, pid) if n["id"] != exclude_id]
            if found:
                raise GraphError(
                    ErrorCode.DUPLICATE_EXACT,
                    f"{spec.name} with natural key {where} exists",
                    hint="Reuse the existing node, or supersede it to record a correction.",
                    details={"node": _strip(found[0])},
                )
        found = (
            [n for n in tx.find_nodes(spec.name, {"dedupe_key": dk}, pid) if n["id"] != exclude_id]
            if dk
            else []
        )
        if found:
            raise GraphError(
                ErrorCode.DUPLICATE_EXACT,
                f"{spec.name} {props.get('title')!r} already exists here",
                hint="Reuse the existing node (update it) instead of creating a new one.",
                details={"node": _strip(found[0])},
            )
        if confirm_new or (
            spec.natural_key and all(props.get(f) is not None for f in spec.natural_key)
        ):
            return
        kind_filter = {"kind": kind} if kind else None
        candidates: list[dict[str, Any]] = []
        for cand in tx.find_nodes(spec.name, kind_filter, pid, limit=1000):
            if cand["id"] == exclude_id:
                continue
            if (
                spec.dedupe_scope == "parent"
                and parent_id
                and self._parent_id(tx, cand["id"]) != parent_id
            ):
                continue
            score = max(
                similarity(props.get("title", ""), t)
                for t in [cand.get("title", ""), *cand.get("aliases", [])]
            )
            if score >= self.similarity_threshold:
                candidates.append({"node": _strip(cand), "score": round(score, 1)})
        if candidates:
            candidates.sort(key=lambda c: -c["score"])
            raise GraphError(
                ErrorCode.DUPLICATE_SIMILAR,
                f"Similar {spec.name} node(s) exist",
                hint="Reuse a candidate, merge, or repeat with confirm_new=true if this is really new.",
                details={"candidates": candidates[:5]},
            )

    def _run_hooks(self, ctx: WriteContext) -> None:
        for h in self.hooks:
            h(ctx)

    # ------------------------------------------------------------------ read operations

    def describe(self) -> dict[str, Any]:
        from florque_graph_core.generate.card import render_card

        return {
            "ontology": self.model.name,
            "ontology_version": self.model.version,
            "mixins_version": self.model.mixins_version,
            "classes": self.model.summary()["classes"],
            "mixins": self.model.summary()["mixins"],
            "card": render_card(self.model),
        }

    def get(self, principal: Principal, node_id: str, depth: int = 1) -> dict[str, Any]:
        depth = max(0, min(depth, 3))

        def run(tx: StoreTx) -> dict[str, Any]:
            node = self._node(tx, node_id)
            self._require_read(principal, node)
            ancestors = []
            cur = node
            seen = {node["id"]}
            while True:
                pid = self._parent_id(tx, cur["id"])
                if pid is None or pid in seen:
                    break
                seen.add(pid)
                parent = tx.get_node(pid)
                if parent is None:
                    break
                ancestors.append(_strip(parent))
                cur = parent
            edges: list[dict[str, Any]] = []
            neighbours: dict[str, dict[str, Any]] = {}
            frontier = [node["id"]]
            visited = {node["id"]}
            for _ in range(depth):
                nxt = []
                for nid in frontier:
                    for e in tx.edges(nid, "both"):
                        edges.append(
                            {"rel": e.rel, "src": e.src, "dst": e.dst, "props": dict(e.props)}
                        )
                        other = e.dst if e.src == nid else e.src
                        if other not in visited:
                            visited.add(other)
                            nxt.append(other)
                if len(visited) > 200:
                    break
                for oid, n in tx.get_nodes(nxt).items():
                    neighbours[oid] = _strip(n)
                frontier = nxt
            uniq = {(e["rel"], e["src"], e["dst"]): e for e in edges}
            return {
                "node": _strip(node),
                "ancestors": ancestors,
                "edges": list(uniq.values()),
                "neighbours": neighbours,
            }

        return self.store.read(run)

    def search(
        self,
        principal: Principal,
        project_id: str,
        query: str,
        cls: str | None = None,
        limit: int = 20,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        if cls is not None:
            resolve_class(self.model, cls)
        if not self.policy.can_read(self._role(principal, project_id)):
            raise GraphError(ErrorCode.FORBIDDEN, f"No access to project {project_id!r}")
        terms = normalize_title(query).split()
        if not terms:
            return {"results": []}

        def run(tx: StoreTx) -> dict[str, Any]:
            rows = tx.search(project_id, terms, cls, limit)
            scored: list[dict[str, Any]] = []
            for n in rows:
                if not include_archived and n.get("status") == "archived":
                    continue
                score = max(
                    similarity(query, t) for t in [n.get("title", ""), *n.get("aliases", [])]
                )
                hits = sum(
                    1
                    for t in terms
                    if t in normalize_title(n.get("title", "") + " " + n.get("summary", ""))
                )
                scored.append({"node": _strip(n), "score": round(score + 10 * hits, 1)})
            scored.sort(key=lambda r: -r["score"])
            return {"results": scored[:limit]}

        return self.store.read(run)

    def find_by_mixin(
        self,
        principal: Principal,
        mixin: str,
        filters: Mapping[str, Any] | None = None,
        project_id: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        if mixin not in self.model.mixins:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Unknown mixin {mixin!r}",
                hint=f"Mixins: {', '.join(self.model.mixins)}",
            )

        def run(tx: StoreTx) -> dict[str, Any]:
            nodes = tx.find_nodes(mixin, dict(filters or {}), project_id, include_archived)
            visible = [
                _strip(n) for n in nodes if self.policy.can_read(self._role_for_node(principal, n))
            ]
            return {"nodes": visible}

        return self.store.read(run)

    def list_nodes(
        self,
        principal: Principal,
        project_id: str,
        cls: str | None = None,
        filters: Mapping[str, Any] | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Nodes of one project, optionally of one class and matching field equality filters."""
        if cls is not None:
            resolve_class(self.model, cls)
        if not self.policy.can_read(self._role(principal, project_id)):
            raise GraphError(ErrorCode.FORBIDDEN, f"No access to project {project_id!r}")
        nodes = self.store.read(
            lambda tx: tx.find_nodes(
                cls or "Node", dict(filters or {}), project_id, include_archived, limit
            )
        )
        return {"nodes": [_strip(n) for n in nodes]}

    def edges_of(
        self,
        principal: Principal,
        node_id: str,
        edge: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Edges touching a node, with the node on the other end."""
        if direction not in ("in", "out", "both"):
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "direction must be in, out or both")
        rel = None
        if edge is not None:
            slot = self.model.slot_for_rel(edge)
            if slot is None:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"Unknown edge {edge!r}")
            rel = self.model.edge_slots()[slot].rel_type

        def run(tx: StoreTx) -> dict[str, Any]:
            node = self._node(tx, node_id)
            self._require_read(principal, node)
            es = tx.edges(node_id, direction, [rel] if rel else None)  # type: ignore[arg-type]
            others = tx.get_nodes([e.dst if e.src == node_id else e.src for e in es])
            out = []
            for e in es:
                oid = e.dst if e.src == node_id else e.src
                if oid in others:
                    out.append(
                        {
                            "rel": e.rel,
                            "src": e.src,
                            "dst": e.dst,
                            "props": dict(e.props),
                            "node": _strip(others[oid]),
                        }
                    )
            return {"edges": out}

        return self.store.read(run)

    def check(self, principal: Principal, project_id: str) -> dict[str, Any]:
        if not self.policy.can_read(self._role(principal, project_id)):
            raise GraphError(ErrorCode.FORBIDDEN, f"No access to project {project_id!r}")

        def run(tx: StoreTx) -> dict[str, Any]:
            rows = tx.run_integrity(self.checks, project_id)
            if rows is None:
                nodes = tx.find_nodes("Node", None, project_id)
                linked: set[str] = set()
                for n in nodes:
                    for e in tx.edges(n["id"], "in"):
                        linked.add(e.src)
                globals_ = [
                    n
                    for n in tx.get_nodes(list(linked)).values()
                    if (s := self.model.cls(n.get("class", ""))) is not None and s.is_global
                ]
                rows = evaluate(tx, self.model, self.checks, [*nodes, *globals_])
            return {"ok": not rows, "violations": rows}

        return self.store.read(run)

    def changes(
        self,
        principal: Principal,
        project_id: str,
        since: int | str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Append-only change log. ``since`` is the cursor (sequence number) from a previous call."""
        if not self.policy.can_read(self._role(principal, project_id)):
            raise GraphError(ErrorCode.FORBIDDEN, f"No access to project {project_id!r}")
        try:
            cursor = int(since) if since not in (None, "") else None
        except (TypeError, ValueError):
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"since must be a cursor (integer), got {since!r}",
                hint="Pass the 'cursor' returned by the previous changes call.",
            ) from None
        rows = self.store.read(lambda tx: tx.changes(project_id, cursor, min(limit, 1000)))
        return {"changes": rows, "cursor": rows[-1]["seq"] if rows else cursor}

    # ------------------------------------------------------------------ create

    def create(
        self,
        principal: Principal,
        cls: str,
        props: Mapping[str, Any],
        parent_id: str | None = None,
        edges: Iterable[Mapping[str, Any]] | None = None,
        idempotency_key: str | None = None,
        confirm_new: bool = False,
        origin: str | None = None,
    ) -> dict[str, Any]:
        requests = _edge_requests(edges)
        idem = self._idem(principal, "create", idempotency_key)
        return self._run_write(
            lambda tx: self._create_in_tx(
                tx, principal, cls, dict(props or {}), parent_id, requests, confirm_new, origin
            ),
            idem,
        )

    def _create_in_tx(
        self,
        tx: StoreTx,
        principal: Principal,
        cls: str,
        props: dict[str, Any],
        parent_id: str | None,
        requests: Sequence[EdgeRequest],
        confirm_new: bool,
        origin: str | None,
        op: str = "create",
    ) -> dict[str, Any]:
        # 1. class and kind
        spec = resolve_class(self.model, cls)
        kind = props.get("kind")
        check_kind(spec, kind)
        # 2. fields
        fields = validate_fields(spec, props, allow_null=False)

        # 5. parent rules (and the project the node belongs to)
        parent: dict[str, Any] | None = None
        if spec.root:
            if parent_id:
                raise GraphError(
                    ErrorCode.PARENT_RULE,
                    f"{spec.name} is the root and has no parent",
                    hint="Omit parent_id.",
                )
        elif parent_id:
            parent = self._node(tx, parent_id)
            self._check_parent(spec, kind, parent)
        elif not spec.is_global:
            allowed = " or ".join(f"{c}:{k}" if k else c for c, k in spec.parent_rules(kind))
            raise GraphError(
                ErrorCode.PARENT_RULE,
                f"A {spec.name}{':' + kind if kind else ''} needs a parent",
                hint=f"Pass parent_id of a {allowed}.",
            )
        node_id = self._new_id(spec.name)
        if spec.root:
            project_id: str | None = node_id
        elif spec.is_global:
            project_id = None
        else:
            assert parent is not None
            project_id = parent.get("project_id")

        # 7. permissions and field ownership
        if spec.root:
            role = (
                "admin"
                if (principal.can_create_projects or principal.role_in(None) == "admin")
                else None
            )
        else:
            role = self._role(principal, project_id)
        if not self.policy.can_create(role, spec.name, kind):
            raise GraphError(
                ErrorCode.FORBIDDEN,
                f"Role {role!r} may not create {spec.name}{':' + kind if kind else ''}",
                hint="Ask a project admin, or record this as a Signal instead.",
            )
        self._check_owners(spec, fields.keys(), role, creating=True)
        fields["status"] = self.policy.initial_status(
            role, principal.is_agent, spec.name, kind, fields.get("status")
        )
        if fields["status"] == "archived":
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "Cannot create an archived node")
        if spec.slots.get("revision") and "revision" not in fields and spec.natural_key:
            fields["revision"] = 1

        # 2/3. required fields and rules on the full node
        check_required(spec, fields)
        check_rules(spec, fields)

        # 4/6. edge typing and project isolation
        resolved = self._check_edges(tx, spec, project_id, requests, principal)
        for req in spec.required_edges(kind):
            if not any(es.slot == req for es, _, _ in resolved):
                raise GraphError(
                    ErrorCode.REQUIRED_EDGE,
                    f"A {spec.name}:{kind} must have a {req} edge at creation",
                    hint=f'Add edges: [{{"type": "{req}", "to": "<id>"}}] (targets: '
                    f"{', '.join(sorted(spec.edges[req].targets))}).",
                )

        self._run_hooks(
            WriteContext(
                op,
                principal,
                role,
                spec,
                dict(fields),
                dict(fields),
                None,
                self.model,
                tx,
                project_id,
            )
        )

        # 8. duplicates
        dk = self._dedupe(spec, kind, parent_id, project_id, fields["title"])
        self._check_duplicates(tx, spec, kind, fields, project_id, parent_id, dk, confirm_new)

        # 9. write
        now = self._now()
        node = {
            **fields,
            "id": node_id,
            "class": spec.name,
            "project_id": project_id,
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "dedupe_key": dk,
        }
        node = {k: v for k, v in node.items() if v is not None}
        tx.create_node(spec.labels, node)
        if parent is not None:
            tx.create_edge(PART_OF, node_id, parent["id"])
        for es, target, eprops in resolved:
            tx.create_edge(es.rel_type, node_id, target["id"], eprops)
        self._log(tx, principal, op, node, fields, origin)
        # 10. integrity on touched nodes
        self._integrity(tx, [node_id])
        return {"node": _strip(node)}

    # ------------------------------------------------------------------ update

    def update(
        self,
        principal: Principal,
        node_id: str,
        patch: Mapping[str, Any],
        if_version: int | None = None,
        idempotency_key: str | None = None,
        origin: str | None = None,
    ) -> dict[str, Any]:
        idem = self._idem(principal, "update", idempotency_key)
        return self._run_write(
            lambda tx: self._update_in_tx(tx, principal, node_id, dict(patch), if_version, origin),
            idem,
        )

    def _update_in_tx(
        self,
        tx: StoreTx,
        principal: Principal,
        node_id: str,
        patch: dict[str, Any],
        if_version: int | None,
        origin: str | None,
    ) -> dict[str, Any]:
        node = self._node(tx, node_id)
        spec = self._spec_of(node)
        role = self._require_read(principal, node)
        if if_version is not None and node.get("version") != if_version:
            raise GraphError(
                ErrorCode.VERSION_CONFLICT,
                f"{node_id} is at version {node.get('version')}, not {if_version}",
                hint="Re-read the node and apply your change to the latest version.",
                details={"current_version": node.get("version")},
            )
        if "kind" in patch and patch["kind"] != node.get("kind"):
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                "kind cannot change",
                hint="Archive this node and create one of the new kind.",
            )
        patch.pop("kind", None)
        fields = validate_fields(spec, patch, allow_null=True)
        changed = {}
        for f, v in fields.items():
            cur = node.get(f)
            slot = spec.slots[f]
            if slot.multivalued and v is not None:
                v = list(dict.fromkeys([*(cur or []), *v]))  # additive
            if v != cur:
                changed[f] = v
        if not changed:
            return {"node": _strip(node), "changed": []}

        self._check_owners(spec, changed.keys(), role, creating=False)
        status = node.get("status", "proposed")
        for f in changed:
            im = spec.slots[f].immutable
            if im == "always" and node.get(f) is not None:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{spec.name}.{f} is immutable")
            if im and im != "always" and STATUS_ORDER.get(status, 0) >= STATUS_ORDER.get(im, 99):
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"{spec.name}.{f} is frozen once the node is {im}",
                    hint="Archive this node and create a new one with the new definition.",
                    details={"field": f},
                )
        if "status" in changed:
            new_status = changed["status"]
            if new_status == "archived":
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    "Use archive to archive a node",
                    hint="Call archive(id).",
                )
            if new_status is None:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "status cannot be cleared")
            reason = self.policy.check_transition(role, node, new_status)
            if reason:
                raise GraphError(
                    ErrorCode.FORBIDDEN, reason, hint="Ask a project admin to make this change."
                )

        merged = {**node}
        for f, v in changed.items():
            if v is None:
                merged.pop(f, None)
            else:
                merged[f] = v
        check_required(spec, merged)
        check_rules(spec, merged)
        self._run_hooks(
            WriteContext(
                "update",
                principal,
                role,
                spec,
                merged,
                changed,
                node,
                self.model,
                tx,
                node.get("project_id"),
            )
        )

        sets: dict[str, Any] = dict(changed)
        if "title" in changed:
            parent_id = self._parent_id(tx, node_id)
            dk = self._dedupe(
                spec, node.get("kind"), parent_id, node.get("project_id"), merged["title"]
            )
            self._check_duplicates(
                tx,
                spec,
                node.get("kind"),
                merged,
                node.get("project_id"),
                parent_id,
                dk,
                True,
                exclude_id=node_id,
            )
            sets["dedupe_key"] = dk
        sets["version"] = node.get("version", 0) + 1
        sets["updated_at"] = self._now()
        if not tx.update_node(node_id, sets, expected_version=node.get("version")):
            raise GraphError(
                ErrorCode.VERSION_CONFLICT,
                f"{node_id} changed concurrently",
                hint="Re-read and retry.",
            )
        self._log(tx, principal, "update", node, changed, origin)
        self._integrity(tx, [node_id])
        after = {**merged, **{k: v for k, v in sets.items() if v is not None}}
        return {"node": _strip(after), "changed": sorted(changed)}

    # ------------------------------------------------------------------ lifecycle

    def archive(
        self, principal: Principal, node_id: str, cascade: bool = False, origin: str | None = None
    ) -> dict[str, Any]:
        return self._run_write(
            lambda tx: self._archive_in_tx(tx, principal, node_id, cascade, origin), None
        )

    def _archive_in_tx(
        self, tx: StoreTx, principal: Principal, node_id: str, cascade: bool, origin: str | None
    ) -> dict[str, Any]:
        node = self._node(tx, node_id)
        role = self._require_read(principal, node)
        if "human" not in self.policy.writable_owners(role) or not self.policy.can_structure(role):
            raise GraphError(ErrorCode.FORBIDDEN, f"Role {role!r} may not archive nodes")
        if node.get("status") == "archived":
            return {"archived": []}
        targets = [node]
        stack = [node_id]
        while stack:
            cur = stack.pop()
            for e in tx.edges(cur, "in", [PART_OF]):
                child = tx.get_node(e.src)
                if child is None or child.get("status") == "archived":
                    continue
                if not cascade:
                    raise GraphError(
                        ErrorCode.PARENT_RULE,
                        f"{node_id} has live children",
                        hint="Archive or move the children first, or pass cascade=true.",
                        details={"child": child["id"]},
                    )
                targets.append(child)
                stack.append(child["id"])
        now = self._now()
        for n in targets:
            tx.update_node(
                n["id"],
                {
                    "status": "archived",
                    "archived_dedupe_key": n.get("dedupe_key"),
                    "dedupe_key": None,
                    "version": n.get("version", 0) + 1,
                    "updated_at": now,
                },
            )
            self._log(tx, principal, "archive", n, {"status": "archived"}, origin)
        return {"archived": [n["id"] for n in targets]}

    def move(self, principal: Principal, node_id: str, new_parent_id: str) -> dict[str, Any]:
        def run(tx: StoreTx) -> dict[str, Any]:
            node = self._node(tx, node_id)
            spec = self._spec_of(node)
            role = self._require_read(principal, node)
            if not self.policy.can_structure(role):
                raise GraphError(ErrorCode.FORBIDDEN, f"Role {role!r} may not move nodes")
            if spec.root:
                raise GraphError(ErrorCode.PARENT_RULE, "The root cannot be moved")
            parent = self._node(tx, new_parent_id)
            self._check_parent(spec, node.get("kind"), parent)
            if not spec.is_global and parent.get("project_id") != node.get("project_id"):
                raise GraphError(
                    ErrorCode.SCOPE_VIOLATION, "Cannot move a node into another project"
                )
            cur: str | None = new_parent_id
            seen: set[str] = set()
            while cur and cur not in seen:
                if cur == node_id:
                    raise GraphError(ErrorCode.PARENT_RULE, "Move would create a cycle")
                seen.add(cur)
                cur = self._parent_id(tx, cur)
            old = self._parent_id(tx, node_id)
            if old == new_parent_id:
                return {"node": _strip(node)}
            if old:
                tx.delete_edge(PART_OF, node_id, old)
            tx.create_edge(PART_OF, node_id, new_parent_id)
            sets: dict[str, Any] = {
                "version": node.get("version", 0) + 1,
                "updated_at": self._now(),
            }
            if spec.dedupe_scope == "parent" and node.get("dedupe_key"):
                dk = self._dedupe(
                    spec, node.get("kind"), new_parent_id, node.get("project_id"), node["title"]
                )
                self._check_duplicates(
                    tx,
                    spec,
                    node.get("kind"),
                    node,
                    node.get("project_id"),
                    new_parent_id,
                    dk,
                    True,
                    exclude_id=node_id,
                )
                sets["dedupe_key"] = dk
            tx.update_node(node_id, sets)
            self._log(tx, principal, "move", node, {"from": old, "to": new_parent_id})
            self._integrity(tx, [node_id])
            return {"node": _strip({**node, **sets})}

        return self._run_write(run, None)

    def supersede(
        self,
        principal: Principal,
        node_id: str,
        patch: Mapping[str, Any],
        origin: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Archive a node and create its next revision in one transaction (metric corrections)."""

        def run(tx: StoreTx) -> dict[str, Any]:
            old = self._node(tx, node_id)
            spec = self._spec_of(old)
            if not spec.natural_key:
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"{spec.name} has no natural key",
                    hint="Use update instead.",
                )
            if old.get("status") == "archived":
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{node_id} is already archived")
            role = self._require_read(principal, old)
            if not self.policy.can_create(role, spec.name, old.get("kind")):
                raise GraphError(ErrorCode.FORBIDDEN, f"Role {role!r} may not create {spec.name}")
            parent_id = self._parent_id(tx, node_id)
            out_edges = [e for e in tx.edges(node_id, "out") if e.rel != PART_OF]
            tx.update_node(
                node_id,
                {
                    "status": "archived",
                    "archived_dedupe_key": old.get("dedupe_key"),
                    "dedupe_key": None,
                    "version": old.get("version", 0) + 1,
                    "updated_at": self._now(),
                },
            )
            self._log(
                tx, principal, "archive", old, {"status": "archived", "superseded": True}, origin
            )
            base = {
                k: v
                for k, v in old.items()
                if k not in SYSTEM_FIELDS and k != "status" and k in spec.slots
            }
            new_props = {**base, **dict(patch)}
            if "revision" in spec.slots:
                new_props["revision"] = int(old.get("revision") or 1) + 1
            requests = []
            for e in out_edges:
                slot = self.model.slot_for_rel(e.rel)
                if slot:
                    requests.append(EdgeRequest(slot, e.dst, dict(e.props)))
            result = self._create_in_tx(
                tx,
                principal,
                spec.name,
                new_props,
                parent_id,
                requests,
                True,
                origin,
                op="supersede",
            )
            return {**result, "superseded": node_id}

        return self._run_write(run, self._idem(principal, "supersede", idempotency_key))

    # ------------------------------------------------------------------ edges

    def link(
        self,
        principal: Principal,
        src_id: str,
        edge: str,
        dst_id: str,
        props: Mapping[str, Any] | None = None,
        origin: str | None = None,
    ) -> dict[str, Any]:
        def run(tx: StoreTx) -> dict[str, Any]:
            src = self._node(tx, src_id)
            spec = self._spec_of(src)
            if src.get("status") == "archived":
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{src_id} is archived")
            self._require_read(principal, src)
            ((es, target, eprops),) = self._check_edges(
                tx,
                spec,
                src.get("project_id"),
                [EdgeRequest(edge, dst_id, dict(props or {}))],
                principal,
            )
            if not es.multivalued:
                for e in tx.edges(src_id, "out", [es.rel_type]):
                    tx.delete_edge(es.rel_type, src_id, e.dst)
            tx.create_edge(es.rel_type, src_id, dst_id, eprops)
            self._log(
                tx, principal, "link", src, {"edge": es.slot, "to": dst_id, "props": eprops}, origin
            )
            self._integrity(tx, [src_id, dst_id])
            return {"edge": {"rel": es.rel_type, "src": src_id, "dst": dst_id, "props": eprops}}

        return self._run_write(run, None)

    def unlink(self, principal: Principal, src_id: str, edge: str, dst_id: str) -> dict[str, Any]:
        def run(tx: StoreTx) -> dict[str, Any]:
            src = self._node(tx, src_id)
            spec = self._spec_of(src)
            role = self._require_read(principal, src)
            slot = self.model.slot_for_rel(edge)
            if slot == "part_of":
                raise GraphError(
                    ErrorCode.PARENT_RULE, "part_of cannot be unlinked", hint="Use move or archive."
                )
            if slot is None or slot not in spec.edges:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{spec.name} has no edge {edge!r}")
            es = spec.edges[slot]
            perm_role = role
            if spec.is_global:
                target = self._node(tx, dst_id)
                perm_role = self._role(principal, target.get("project_id"))
            if not self.policy.can_link(perm_role, slot):
                raise GraphError(
                    ErrorCode.FORBIDDEN, f"Role {perm_role!r} may not remove {slot} edges"
                )
            existing = tx.edges(src_id, "out", [es.rel_type])
            if not any(e.dst == dst_id for e in existing):
                raise GraphError(ErrorCode.NOT_FOUND, f"No {slot} edge {src_id} -> {dst_id}")
            if (
                slot in spec.required_edges(src.get("kind"))
                and src.get("status") != "archived"
                and len(existing) <= 1
            ):
                raise GraphError(
                    ErrorCode.REQUIRED_EDGE,
                    f"{spec.name}:{src.get('kind')} must keep at least one {slot} edge",
                    hint=f"Link another {slot} target first, then unlink this one.",
                )
            tx.delete_edge(es.rel_type, src_id, dst_id)
            self._log(tx, principal, "unlink", src, {"edge": slot, "to": dst_id})
            return {"removed": {"rel": es.rel_type, "src": src_id, "dst": dst_id}}

        return self._run_write(run, None)

    # ------------------------------------------------------------------ merge

    def merge(self, principal: Principal, keep_id: str, drop_id: str) -> dict[str, Any]:
        def run(tx: StoreTx) -> dict[str, Any]:
            if keep_id == drop_id:
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "keep and drop are the same node")
            keep, drop = self._node(tx, keep_id), self._node(tx, drop_id)
            spec = self._spec_of(keep)
            role = self._require_read(principal, keep)
            self._require_read(principal, drop)
            if not self.policy.can_structure(role) or "human" not in self.policy.writable_owners(
                role
            ):
                raise GraphError(ErrorCode.FORBIDDEN, f"Role {role!r} may not merge nodes")
            if (keep["class"], keep.get("kind")) != (drop["class"], drop.get("kind")):
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    "Only nodes of the same class and kind can be merged",
                )
            if keep.get("project_id") != drop.get("project_id"):
                raise GraphError(ErrorCode.SCOPE_VIOLATION, "Cannot merge across projects")
            if "archived" in (keep.get("status"), drop.get("status")):
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "Cannot merge archived nodes")

            sets: dict[str, Any] = {}
            conflicts: list[str] = []
            for f, slot in spec.slots.items():
                if slot.owner == "system" or f in ("title", "kind"):
                    continue
                kv, dv = keep.get(f), drop.get(f)
                if dv is None or dv == kv:
                    continue
                if kv is None:
                    sets[f] = dv
                elif slot.multivalued:
                    sets[f] = list(dict.fromkeys([*kv, *dv]))
                elif f == "summary" and spec.merge == "additive":
                    sets[f] = f"{kv}\n\n{dv}"
                elif f == "status":
                    if STATUS_ORDER.get(dv, 0) > STATUS_ORDER.get(kv, 0):
                        sets[f] = dv
                else:
                    conflicts.append(f)
            if conflicts:
                raise GraphError(
                    ErrorCode.MERGE_CONFLICT,
                    f"Conflicting values for {', '.join(conflicts)}",
                    hint="Resolve the conflicting fields with update on either node, then merge again.",
                    details={
                        "fields": {f: {"keep": keep.get(f), "drop": drop.get(f)} for f in conflicts}
                    },
                )
            aliases = list(
                dict.fromkeys(
                    [
                        *(sets.get("aliases") or keep.get("aliases") or []),
                        drop["title"],
                        *drop.get("aliases", []),
                    ]
                )
            )
            sets["aliases"] = [a for a in aliases if a != keep["title"]]

            # redirect edges
            for e in tx.edges(drop_id, "both"):
                if e.src == drop_id and e.rel == PART_OF:
                    continue
                src = keep_id if e.src == drop_id else e.src
                dst = keep_id if e.dst == drop_id else e.dst
                tx.delete_edge(e.rel, e.src, e.dst)
                if src != dst:
                    tx.create_edge(e.rel, src, dst, dict(e.props))
            sets["version"] = keep.get("version", 0) + 1
            sets["updated_at"] = self._now()
            tx.update_node(keep_id, sets)
            tx.update_node(
                drop_id,
                {
                    "status": "archived",
                    "archived_dedupe_key": drop.get("dedupe_key"),
                    "dedupe_key": None,
                    "version": drop.get("version", 0) + 1,
                    "updated_at": sets["updated_at"],
                },
            )
            self._log(tx, principal, "merge", keep, {"dropped": drop_id, "set": sorted(sets)})
            self._log(tx, principal, "archive", drop, {"merged_into": keep_id})
            self._integrity(tx, [keep_id])
            return {"node": _strip({**keep, **sets}), "dropped": drop_id}

        return self._run_write(run, None)
