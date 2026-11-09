"""FlorqueApp: the one wiring of graph-core + workgraph-domain + signal-hub.

Both the in-process client and the HTTP service call ``FlorqueApp.call`` so the
agent-facing contract is identical in local and remote mode (spec goal 5).

Every project runs on its effective ontology: the base workgraph ontology plus the
active extensions of its tenant and of the project itself. One GraphCore is compiled per
distinct extension set and cached; all of them share one graph store.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from florque_graph_core import GraphCore, Principal
from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.ontology.loader import OntologyLoadError, parse_extension
from florque_graph_core.ontology.model import SYSTEM_FIELDS
from florque_graph_core.store.base import GraphStore
from florque_signal_hub import HubConfig, SignalHub, SQLiteHubStore
from florque_signal_hub.contract import ContractError, verify_contract
from florque_signal_hub.store.repository import HubStore
from florque_workgraph_domain import build_core
from florque_workgraph_domain.recipes import list_recipes, run_recipe

from florque_client.config import Config
from florque_client.ontologies import RegistryConflict, SQLiteOntologyRegistry

DEFAULT_TENANT = "default"
_SYSTEM = {*SYSTEM_FIELDS, "status"}
NODE_ARGS = ("node_id", "kr_id", "task_id")


def make_graph_store(cfg: Config) -> GraphStore:
    if cfg.store == "memory":
        from florque_graph_core.store.memory import MemoryStore

        return MemoryStore()
    if cfg.store == "file":
        from florque_graph_core.store.memory import MemoryStore

        Path(cfg.data_file).parent.mkdir(parents=True, exist_ok=True)
        return MemoryStore(cfg.data_file)
    if cfg.store == "neo4j":
        from florque_graph_core.store.neo4j import Neo4jStore

        if not cfg.neo4j_password:
            raise RuntimeError(
                "NEO4J_PASSWORD is not set (or use FLORQUE_STORE=file for a file-backed local graph)"
            )
        return Neo4jStore(cfg.neo4j_uri, cfg.neo4j_user, cfg.neo4j_password, cfg.neo4j_database)
    raise RuntimeError(f"Unknown graph store {cfg.store!r}")


def _tenant(p: Principal) -> str:
    return p.tenant_id or DEFAULT_TENANT


class FlorqueApp:
    def __init__(
        self,
        core: GraphCore,
        hub: SignalHub,
        registry: SQLiteOntologyRegistry | None = None,
        core_factory: Callable[[tuple[str, ...]], GraphCore] | None = None,
    ) -> None:
        self.core = core  # base ontology; the hub always works through it
        self.hub = hub
        self.registry = registry or SQLiteOntologyRegistry()
        self._factory = core_factory
        self._cores: dict[tuple[str, ...], GraphCore] = {(): core}
        self._lock = threading.Lock()
        c = self._core_for_project
        n = self._core_for_node
        self.ops: dict[str, Callable[..., Any]] = {
            "describe": lambda p, project_id=None: self._describe(p, project_id),
            "projects": lambda p, include_archived=False: core.list_projects(
                p, bool(include_archived)
            ),
            "get": lambda p, node_id, depth=1: n(node_id).get(p, node_id, int(depth)),
            "search": lambda p, project_id, query, cls=None, limit=20: c(project_id).search(
                p, project_id, query, cls, int(limit)
            ),
            "list_nodes": lambda p, project_id, cls=None, filters=None, include_archived=False: c(
                project_id
            ).list_nodes(p, project_id, cls, filters, bool(include_archived)),
            "create": lambda p, cls, props, parent_id=None, edges=None, idempotency_key=None, confirm_new=False: (
                (n(parent_id) if parent_id else self._core_for_tenant(_tenant(p))).create(
                    p, cls, props, parent_id, edges, idempotency_key, bool(confirm_new)
                )
            ),
            "update": lambda p, node_id, patch, if_version=None, idempotency_key=None: n(
                node_id
            ).update(p, node_id, patch, if_version, idempotency_key),
            "archive": lambda p, node_id, cascade=False: n(node_id).archive(
                p, node_id, bool(cascade)
            ),
            "move": lambda p, node_id, new_parent_id: n(node_id).move(p, node_id, new_parent_id),
            "link": lambda p, src, edge, dst, props=None: n(src).link(p, src, edge, dst, props),
            "unlink": lambda p, src, edge, dst: n(src).unlink(p, src, edge, dst),
            "merge": lambda p, keep, drop: n(keep).merge(p, keep, drop),
            "check": lambda p, project_id: c(project_id).check(p, project_id),
            "changes": lambda p, project_id, since=None, limit=100: c(project_id).changes(
                p, project_id, since, int(limit)
            ),
            "recipes": lambda p: {"recipes": list_recipes()},
            "recipe": lambda p, name, args=None: self._recipe(p, name, dict(args or {})),
            # ontology extensions
            "ontology_extensions": lambda p, project_id=None, include_retired=False: (
                self._extensions(p, project_id, bool(include_retired))
            ),
            "ontology_validate": lambda p, yaml, project_id=None: self._validate(
                p, yaml, project_id
            ),
            "ontology_add": lambda p, yaml, project_id=None: self._add_extension(
                p, yaml, project_id
            ),
            "ontology_retire": lambda p, id: self._retire_extension(p, id),
            # hub
            "hub_ingest": lambda p, observation: hub.ingest(p, observation),
            "hub_sources": lambda p: hub.list_sources(p),
            "hub_source_add": lambda p, id, kind, name=None, config=None: hub.add_source(
                p, id, kind, name, config
            ),
            "hub_source_archive": lambda p, id: hub.archive_source(p, id),
            "hub_sensors": lambda p, project_id=None: hub.list_sensors(p, project_id),
            "hub_sensor_add": lambda p, series_code, project_id, unit, aggregation="last", source_id=None, description=None: (
                hub.add_sensor(
                    p, series_code, project_id, unit, aggregation, source_id, description
                )
            ),
            "hub_sensor_archive": lambda p, id: hub.archive_sensor(p, id),
            "hub_bindings": lambda p, kind="channel": hub.list_bindings(p, kind),
            "hub_binding_add": lambda p, kind, binding: hub.add_binding(p, kind, binding),
            "hub_binding_archive": lambda p, kind, id: hub.archive_binding(p, kind, id),
            "hub_inbox": lambda p, status="open": hub.inbox(p, status),
            "hub_inbox_resolve": lambda p, id, action, node_id=None: hub.resolve_inbox(
                p, id, action, node_id
            ),
            "hub_evaluate": lambda p, node_id=None, project_id=None: self._evaluate(
                p, node_id, project_id
            ),
            "hub_reconcile": lambda p: self._admin_only(p, hub.reconcile),
        }

    # ------------------------------------------------------------------ ontology resolution

    @property
    def ontology_version(self) -> str:
        return self.core.model.version

    def _compile(self, texts: tuple[str, ...]) -> GraphCore:
        """A GraphCore for base + these extensions; verifies the hub's mixin contract."""
        if self._factory is None:
            raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, "Ontology extensions are not enabled")
        try:
            core = self._factory(texts)
            verify_contract(core.describe())
        except OntologyLoadError as e:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Extension rejected: {e}",
                hint="Extensions may add classes, slots, enums and enum values; see fwg ontology show.",
            ) from e
        except ContractError as e:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Extension breaks the hub contract: {e}",
                hint="Do not change the Expectation or Observation mixins.",
            ) from e
        core.register_hook(self.hub.series_code_hook)
        return core

    def _core_for_exts(self, rows: list[dict[str, Any]]) -> GraphCore:
        key = tuple(r["id"] for r in rows)
        with self._lock:
            core = self._cores.get(key)
        if core is None:
            core = self._compile(tuple(r["yaml"] for r in rows))
            with self._lock:
                core = self._cores.setdefault(key, core)
        return core

    def _core_for_tenant(self, tenant: str) -> GraphCore:
        return self._core_for_exts(self.registry.active(tenant, None))

    def _raw_node(self, node_id: str) -> dict[str, Any] | None:
        return self.core.store.read(lambda tx: tx.get_node(node_id))

    def _core_for_project(self, project_id: str) -> GraphCore:
        node = self._raw_node(project_id)
        if node is None:
            return self.core  # the base core reports NOT_FOUND / FORBIDDEN as usual
        tenant = node.get("tenant_id") or DEFAULT_TENANT
        return self._core_for_exts(self.registry.active(tenant, node.get("project_id")))

    def _core_for_node(self, node_id: str) -> GraphCore:
        node = self._raw_node(node_id)
        if node is None:
            return self.core
        tenant = node.get("tenant_id") or DEFAULT_TENANT
        return self._core_for_exts(self.registry.active(tenant, node.get("project_id")))

    def _core_for_call(self, p: Principal, op: str, args: Mapping[str, Any]) -> GraphCore:
        """The core whose ontology version is reported for this call."""
        if args.get("project_id"):
            return self._core_for_project(str(args["project_id"]))
        for key in ("node_id", "src", "keep", "parent_id"):
            if args.get(key):
                return self._core_for_node(str(args[key]))
        if op == "recipe":
            return self._recipe_core(dict(args.get("args") or {}))
        if op == "create" or op.startswith("ontology_"):
            return self._core_for_tenant(_tenant(p))
        return self.core

    def _recipe_core(self, args: dict[str, Any]) -> GraphCore:
        if args.get("project_id"):
            return self._core_for_project(str(args["project_id"]))
        for key in NODE_ARGS:
            if args.get(key):
                return self._core_for_node(str(args[key]))
        return self.core

    # ------------------------------------------------------------------ ops

    def _describe(self, p: Principal, project_id: str | None) -> dict[str, Any]:
        if project_id is None:
            return self._core_for_tenant(_tenant(p)).describe()
        core = self._core_for_project(project_id)
        core.get(p, project_id, depth=0)  # visible to the caller
        return core.describe()

    def _recipe(self, p: Principal, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return run_recipe(self._recipe_core(args), p, name, args)

    def _admin_only(self, p: Principal, fn: Callable[[], Any]) -> Any:
        if self.core.role(p, None) != "admin" or p.tenant_id is not None:
            raise GraphError(ErrorCode.FORBIDDEN, "Operator only")
        return fn()

    def _evaluate(self, p: Principal, node_id: str | None, project_id: str | None) -> Any:
        if node_id:
            node = self.core.get(p, node_id, depth=0)["node"]
            project_id = node.get("project_id")
        if self.core.role(p, project_id) not in ("admin", "hub"):
            raise GraphError(ErrorCode.FORBIDDEN, "Only an admin or the hub triggers evaluation")
        if node_id:
            return self.hub.evaluate_one(node_id)
        if project_id is None and p.tenant_id is not None:
            projects = self.core.list_projects(p)["projects"]
            results = [self.hub.evaluate_all(pr["id"]) for pr in projects]
            return {
                "evaluated": sum(r["evaluated"] for r in results),
                "results": [x for r in results for x in r["results"]],
            }
        return self.hub.evaluate_all(project_id)

    # ------------------------------------------------------------------ extensions

    def _require_scope_admin(self, p: Principal, project_id: str | None) -> None:
        if project_id is not None:
            self.core.get(p, project_id, depth=0)  # NOT_FOUND for other tenants
            if self.core.model.root_class != (self._raw_node(project_id) or {}).get("class"):
                raise GraphError(ErrorCode.ONTOLOGY_VIOLATION, f"{project_id} is not a project")
        if self.core.role(p, project_id) != "admin":
            raise GraphError(ErrorCode.FORBIDDEN, "Ontology extensions need an admin")

    def _extensions(
        self, p: Principal, project_id: str | None, include_retired: bool
    ) -> dict[str, Any]:
        if project_id is not None:
            self.core.get(p, project_id, depth=0)
        elif not self.core.policy.can_read(self.core.role(p, None)):
            raise GraphError(ErrorCode.FORBIDDEN, "No access")
        rows = self.registry.list(_tenant(p), project_id, include_retired)
        return {"extensions": [{k: v for k, v in r.items() if k != "yaml"} for r in rows]}

    def _scope_projects(self, p: Principal, project_id: str | None) -> list[str]:
        if project_id is not None:
            return [project_id]
        tenant = p.tenant_id
        projects = self.core.list_projects(p, include_archived=True)["projects"]
        return [pr["id"] for pr in projects if pr.get("tenant_id") == tenant]

    def _dry_run(self, core: GraphCore, project_ids: list[str], tenant: str | None) -> list[str]:
        """Existing nodes that the candidate ontology would not accept."""
        model = core.model
        problems: list[str] = []

        def scan(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                spec = model.cls(node.get("class", ""))
                if spec is None:
                    problems.append(f"{node['id']}: class {node.get('class')} would disappear")
                    continue
                if spec.kinds is not None and node.get("kind") not in spec.kinds:
                    problems.append(f"{node['id']}: kind {node.get('kind')} would disappear")
                for f in node:
                    if f not in spec.slots and f not in _SYSTEM and f != "kind":
                        problems.append(f"{node['id']}: field {f} would disappear")

        def nodes(label: str, where: dict[str, Any] | None, pid: str | None) -> Any:
            return self.core.store.read(lambda tx: tx.find_nodes(label, where, pid, True))

        for pid in project_ids:
            scan(nodes("Node", None, pid))
        for spec in self.core.model.concrete():
            if spec.is_global:
                scan(nodes(spec.name, {"tenant_id": tenant} if tenant else None, None))
        return problems[:50]

    def _candidate(
        self, p: Principal, project_id: str | None, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        core = self._compile(tuple(r["yaml"] for r in rows))
        problems = self._dry_run(core, self._scope_projects(p, project_id), p.tenant_id)
        if problems:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                "Existing nodes do not fit the new ontology",
                hint="Archive or change those nodes first, or keep the classes and fields they use.",
                details={"problems": problems},
            )
        base = self.core.model
        added = sorted(set(core.model.classes) - set(base.classes))
        kinds = {
            c.name: sorted(set(c.kinds or {}) - set(base.classes[c.name].kinds or {}))
            for c in core.model.concrete()
            if c.name in base.classes and set(c.kinds or {}) - set(base.classes[c.name].kinds or {})
        }
        return {
            "ontology_version": core.model.version,
            "classes_added": added,
            "kinds_added": kinds,
        }

    def _scope_rows(
        self, p: Principal, project_id: str | None, replacing: str | None
    ) -> list[dict[str, Any]]:
        tenant = _tenant(p)
        if project_id is None:
            rows = self.registry.active(tenant, None)
        else:
            rows = self.registry.active(tenant, project_id)
        return [r for r in rows if r["name"] != replacing]

    def _parse(self, text: str) -> Any:
        try:
            return parse_extension(text)
        except OntologyLoadError as e:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION, f"Extension rejected: {e}", hint="Fix the YAML."
            ) from e

    def _validate(self, p: Principal, text: str, project_id: str | None) -> dict[str, Any]:
        self._require_scope_admin(p, project_id)
        ext = self._parse(text)
        rows = self._scope_rows(p, project_id, ext.name)
        if project_id is not None:  # a project extension cannot shadow a tenant one
            tenant_rows = self.registry.active(_tenant(p), None)
            if any(r["name"] == ext.name for r in tenant_rows):
                raise GraphError(
                    ErrorCode.DUPLICATE_EXACT,
                    f"The tenant already has an extension named {ext.name}",
                    hint="Pick another name for the project extension.",
                )
        candidate = rows + [{"id": "candidate", "yaml": text, "name": ext.name}]
        return {
            "name": ext.name,
            "version": ext.version,
            **self._candidate(p, project_id, candidate),
        }

    def _add_extension(self, p: Principal, text: str, project_id: str | None) -> dict[str, Any]:
        result = self._validate(p, text, project_id)
        try:
            row = self.registry.add(
                _tenant(p), project_id, result["name"], result["version"], text, p.actor_id
            )
        except RegistryConflict as e:
            raise GraphError(
                ErrorCode.DUPLICATE_EXACT,
                str(e),
                hint="Bump the extension version to publish a change.",
            ) from e
        return {**result, "extension": {k: v for k, v in row.items() if k != "yaml"}}

    def _retire_extension(self, p: Principal, ext_id: str) -> dict[str, Any]:
        row = self.registry.get(ext_id)
        if row is None or row["tenant_id"] != _tenant(p) or row["status"] != "active":
            raise GraphError(ErrorCode.NOT_FOUND, f"Active extension {ext_id!r} not found")
        self._require_scope_admin(p, row["project_id"])
        remaining = self._scope_rows(p, row["project_id"], row["name"])
        if row["project_id"] is None:
            # every project that adds its own extensions must still compile without this one
            for pid in self._scope_projects(p, None):
                project_rows = [
                    r for r in self.registry.active(_tenant(p), pid) if r["id"] != ext_id
                ]
                if any(r["project_id"] for r in project_rows):
                    self._candidate(p, pid, project_rows)
        result = self._candidate(p, row["project_id"], remaining)
        self.registry.retire(ext_id)
        return {"retired": ext_id, "ontology_version": result["ontology_version"]}

    # ------------------------------------------------------------------ dispatch

    def call(self, principal: Principal, op: str, **args: Any) -> dict[str, Any]:
        fn = self.ops.get(op)
        base = {"ontology_version": self.ontology_version}
        if fn is None:
            err = GraphError(
                ErrorCode.NOT_FOUND,
                f"Unknown operation {op!r}",
                hint=f"Operations: {', '.join(self.ops)}",
            )
            return {"ok": False, "error": err.to_dict(), **base}
        try:
            inspect.signature(fn).bind(principal, **args)
        except TypeError as e:
            err = GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Bad arguments for {op}: {e}",
                hint="Check the command usage.",
            )
            return {"ok": False, "error": err.to_dict(), **base}
        try:
            data = fn(principal, **args)
            version = self._core_for_call(principal, op, args).model.version
            return {"ok": True, "data": data, "ontology_version": version}
        except GraphError as e:
            return {"ok": False, "error": e.to_dict(), **base}

    def close(self) -> None:
        self.core.store.close()
        self.hub.store.close()
        self.registry.close()


def build_app(
    cfg: Config | None = None,
    *,
    graph_store: GraphStore | None = None,
    hub_store: HubStore | None = None,
    hub_config: HubConfig | None = None,
    registry: SQLiteOntologyRegistry | None = None,
    **core_kwargs: Any,
) -> FlorqueApp:
    cfg = cfg or Config(store="memory", hub_db=":memory:", ontology_db=":memory:")
    graph_store = graph_store or make_graph_store(cfg)
    if hub_store is None:
        if cfg.hub_db != ":memory:":
            Path(cfg.hub_db).parent.mkdir(parents=True, exist_ok=True)
        hub_store = SQLiteHubStore(cfg.hub_db)
    registry = registry or SQLiteOntologyRegistry(cfg.ontology_db)
    core = build_core(graph_store, **core_kwargs)
    hub = SignalHub(core, hub_store, hub_config)
    core.register_hook(hub.series_code_hook)

    def factory(texts: tuple[str, ...]) -> GraphCore:
        return build_core(graph_store, extensions=texts, **core_kwargs)

    return FlorqueApp(core, hub, registry, factory)
