"""The client interface shared by the in-process and HTTP implementations (spec 8).

Every method returns the response envelope:
{"ok": true, "data": ..., "ontology_version": "..."} or
{"ok": false, "error": {"code", "message", "hint", "details"}, "ontology_version": "..."}.
"""

from __future__ import annotations

from typing import Any


class Client:
    """Operations mirror graph-core plus recipes and hub. Subclasses implement ``_call``."""

    def _call(self, op: str, **args: Any) -> dict[str, Any]:
        raise NotImplementedError

    # graph
    def describe(self) -> dict[str, Any]:
        return self._call("describe")

    def get(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        return self._call("get", node_id=node_id, depth=depth)

    def search(
        self, project_id: str, query: str, cls: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        return self._call("search", project_id=project_id, query=query, cls=cls, limit=limit)

    def list_nodes(
        self,
        project_id: str,
        cls: str | None = None,
        filters: dict[str, Any] | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        return self._call(
            "list_nodes",
            project_id=project_id,
            cls=cls,
            filters=filters,
            include_archived=include_archived,
        )

    def create(
        self,
        cls: str,
        props: dict[str, Any],
        parent_id: str | None = None,
        edges: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        confirm_new: bool = False,
    ) -> dict[str, Any]:
        return self._call(
            "create",
            cls=cls,
            props=props,
            parent_id=parent_id,
            edges=edges,
            idempotency_key=idempotency_key,
            confirm_new=confirm_new,
        )

    def update(
        self,
        node_id: str,
        patch: dict[str, Any],
        if_version: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "update",
            node_id=node_id,
            patch=patch,
            if_version=if_version,
            idempotency_key=idempotency_key,
        )

    def archive(self, node_id: str, cascade: bool = False) -> dict[str, Any]:
        return self._call("archive", node_id=node_id, cascade=cascade)

    def move(self, node_id: str, new_parent_id: str) -> dict[str, Any]:
        return self._call("move", node_id=node_id, new_parent_id=new_parent_id)

    def link(
        self, src: str, edge: str, dst: str, props: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._call("link", src=src, edge=edge, dst=dst, props=props)

    def unlink(self, src: str, edge: str, dst: str) -> dict[str, Any]:
        return self._call("unlink", src=src, edge=edge, dst=dst)

    def merge(self, keep: str, drop: str) -> dict[str, Any]:
        return self._call("merge", keep=keep, drop=drop)

    def check(self, project_id: str) -> dict[str, Any]:
        return self._call("check", project_id=project_id)

    def changes(
        self, project_id: str, since: int | None = None, limit: int = 100
    ) -> dict[str, Any]:
        return self._call("changes", project_id=project_id, since=since, limit=limit)

    def recipes(self) -> dict[str, Any]:
        return self._call("recipes")

    def recipe(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._call("recipe", name=name, args=args or {})

    # hub
    def hub_ingest(self, observation: dict[str, Any]) -> dict[str, Any]:
        return self._call("hub_ingest", observation=observation)

    def hub_sources(self) -> dict[str, Any]:
        return self._call("hub_sources")

    def hub_source_add(
        self, id: str, kind: str, name: str | None = None, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._call("hub_source_add", id=id, kind=kind, name=name, config=config)

    def hub_source_archive(self, id: str) -> dict[str, Any]:
        return self._call("hub_source_archive", id=id)

    def hub_sensors(self, project_id: str | None = None) -> dict[str, Any]:
        return self._call("hub_sensors", project_id=project_id)

    def hub_sensor_add(
        self,
        series_code: str,
        project_id: str,
        unit: str,
        aggregation: str = "last",
        source_id: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        return self._call(
            "hub_sensor_add",
            series_code=series_code,
            project_id=project_id,
            unit=unit,
            aggregation=aggregation,
            source_id=source_id,
            description=description,
        )

    def hub_sensor_archive(self, id: str) -> dict[str, Any]:
        return self._call("hub_sensor_archive", id=id)

    def hub_bindings(self, kind: str = "channel") -> dict[str, Any]:
        return self._call("hub_bindings", kind=kind)

    def hub_binding_add(self, kind: str, binding: dict[str, Any]) -> dict[str, Any]:
        return self._call("hub_binding_add", kind=kind, binding=binding)

    def hub_binding_archive(self, kind: str, id: str) -> dict[str, Any]:
        return self._call("hub_binding_archive", kind=kind, id=id)

    def hub_inbox(self, status: str | None = "open") -> dict[str, Any]:
        return self._call("hub_inbox", status=status)

    def hub_inbox_resolve(self, id: str, action: str, node_id: str | None = None) -> dict[str, Any]:
        return self._call("hub_inbox_resolve", id=id, action=action, node_id=node_id)

    def hub_evaluate(
        self, node_id: str | None = None, project_id: str | None = None
    ) -> dict[str, Any]:
        return self._call("hub_evaluate", node_id=node_id, project_id=project_id)

    def hub_reconcile(self) -> dict[str, Any]:
        return self._call("hub_reconcile")

    def close(self) -> None:  # pragma: no cover - trivial
        pass
