"""FlorqueApp: the one wiring of graph-core + workgraph + signal-hub.

Both the in-process client and the HTTP service call ``FlorqueApp.call`` so the
agent-facing contract is identical in local and remote mode (spec goal 5).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from florque_graph_core import GraphCore, Principal
from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.store.base import GraphStore
from florque_signal_hub import HubConfig, SignalHub, SQLiteHubStore
from florque_signal_hub.store.repository import HubStore
from florque_workgraph_domain import build_core
from florque_workgraph_domain.recipes import list_recipes, run_recipe

from florque_client.config import Config


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


class FlorqueApp:
    def __init__(self, core: GraphCore, hub: SignalHub) -> None:
        self.core = core
        self.hub = hub
        self.ops: dict[str, Callable[..., Any]] = {
            "describe": lambda p: core.describe(),
            "get": lambda p, node_id, depth=1: core.get(p, node_id, int(depth)),
            "search": lambda p, project_id, query, cls=None, limit=20: core.search(
                p, project_id, query, cls, int(limit)
            ),
            "list_nodes": lambda p, project_id, cls=None, filters=None, include_archived=False: (
                core.list_nodes(p, project_id, cls, filters, bool(include_archived))
            ),
            "create": lambda p, cls, props, parent_id=None, edges=None, idempotency_key=None, confirm_new=False: (
                core.create(p, cls, props, parent_id, edges, idempotency_key, bool(confirm_new))
            ),
            "update": lambda p, node_id, patch, if_version=None, idempotency_key=None: core.update(
                p, node_id, patch, if_version, idempotency_key
            ),
            "archive": lambda p, node_id, cascade=False: core.archive(p, node_id, bool(cascade)),
            "move": lambda p, node_id, new_parent_id: core.move(p, node_id, new_parent_id),
            "link": lambda p, src, edge, dst, props=None: core.link(p, src, edge, dst, props),
            "unlink": lambda p, src, edge, dst: core.unlink(p, src, edge, dst),
            "merge": lambda p, keep, drop: core.merge(p, keep, drop),
            "check": lambda p, project_id: core.check(p, project_id),
            "changes": lambda p, project_id, since=None, limit=100: core.changes(
                p, project_id, since, int(limit)
            ),
            "recipes": lambda p: {"recipes": list_recipes()},
            "recipe": lambda p, name, args=None: run_recipe(core, p, name, dict(args or {})),
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

    @property
    def ontology_version(self) -> str:
        return self.core.model.version

    def _admin_only(self, p: Principal, fn: Callable[[], Any]) -> Any:
        if self.core.role(p, None) != "admin":
            raise GraphError(ErrorCode.FORBIDDEN, "Admin only")
        return fn()

    def _evaluate(self, p: Principal, node_id: str | None, project_id: str | None) -> Any:
        if self.core.role(p, project_id) not in ("admin", "hub"):
            raise GraphError(ErrorCode.FORBIDDEN, "Only an admin or the hub triggers evaluation")
        return self.hub.evaluate_one(node_id) if node_id else self.hub.evaluate_all(project_id)

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
            return {"ok": True, "data": fn(principal, **args), **base}
        except GraphError as e:
            return {"ok": False, "error": e.to_dict(), **base}

    def close(self) -> None:
        self.core.store.close()
        self.hub.store.close()


def build_app(
    cfg: Config | None = None,
    *,
    graph_store: GraphStore | None = None,
    hub_store: HubStore | None = None,
    hub_config: HubConfig | None = None,
    **core_kwargs: Any,
) -> FlorqueApp:
    cfg = cfg or Config(store="memory", hub_db=":memory:")
    graph_store = graph_store or make_graph_store(cfg)
    if hub_store is None:
        if cfg.hub_db != ":memory:":
            Path(cfg.hub_db).parent.mkdir(parents=True, exist_ok=True)
        hub_store = SQLiteHubStore(cfg.hub_db)
    core = build_core(graph_store, **core_kwargs)
    hub = SignalHub(core, hub_store, hub_config)
    core.register_hook(hub.series_code_hook)
    return FlorqueApp(core, hub)
