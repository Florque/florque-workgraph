"""HTTP client against the florque-service /v1 API (remote mode)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from florque_client.base import Client


def _q(s: str) -> str:
    return quote(s, safe="")


class HttpClient(Client):
    def __init__(
        self,
        base_url: str = "",
        token: str | None = None,
        http: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = http or httpx.Client(base_url=base_url, timeout=timeout)
        self.http.headers.update(headers)

    def _req(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = self.http.request(method, path, params=params, json=json, headers=headers)
        except httpx.HTTPError as e:
            return {
                "ok": False,
                "error": {
                    "code": "UNAVAILABLE",
                    "message": str(e),
                    "hint": "Check FLORQUE_API_URL.",
                    "details": {},
                },
            }
        try:
            return r.json()  # type: ignore[no-any-return]
        except ValueError:
            return {
                "ok": False,
                "error": {
                    "code": "UNAVAILABLE",
                    "message": f"HTTP {r.status_code}",
                    "hint": "",
                    "details": {},
                },
            }

    def _call(self, op: str, **a: Any) -> dict[str, Any]:  # noqa: C901 - a flat routing table
        if op == "describe":
            return self._req("GET", "/v1/ontology")
        if op == "get":
            return self._req(
                "GET", f"/v1/nodes/{_q(a['node_id'])}", params={"depth": a.get("depth", 1)}
            )
        if op == "search":
            return self._req(
                "GET",
                "/v1/search",
                params={
                    "project_id": a["project_id"],
                    "q": a["query"],
                    "cls": a.get("cls"),
                    "limit": a.get("limit"),
                },
            )
        if op == "list_nodes":
            return self._req("POST", "/v1/nodes:list", json=a)
        if op == "create":
            body = {k: a.get(k) for k in ("cls", "props", "parent_id", "edges", "confirm_new")}
            path = "/v1/projects" if a["cls"] == "Project" else "/v1/nodes"
            return self._req("POST", path, json=body, idempotency_key=a.get("idempotency_key"))
        if op == "update":
            return self._req(
                "PATCH",
                f"/v1/nodes/{_q(a['node_id'])}",
                json={"patch": a["patch"], "if_version": a.get("if_version")},
                idempotency_key=a.get("idempotency_key"),
            )
        if op == "archive":
            return self._req(
                "POST",
                f"/v1/nodes/{_q(a['node_id'])}:archive",
                json={"cascade": a.get("cascade", False)},
            )
        if op == "move":
            return self._req(
                "POST",
                f"/v1/nodes/{_q(a['node_id'])}:move",
                json={"new_parent_id": a["new_parent_id"]},
            )
        if op == "link":
            return self._req("POST", "/v1/edges", json=a)
        if op == "unlink":
            return self._req("POST", "/v1/edges:unlink", json=a)
        if op == "merge":
            return self._req("POST", "/v1/merge", json=a)
        if op == "check":
            return self._req("POST", "/v1/check", json=a)
        if op == "changes":
            return self._req("GET", "/v1/changes", params=a)
        if op == "recipes":
            return self._req("GET", "/v1/recipes")
        if op == "recipe":
            return self._req("GET", f"/v1/recipes/{_q(a['name'])}", params=a.get("args") or {})
        if op == "hub_ingest":
            return self._req("POST", "/v1/hub/observations", json=a["observation"])
        if op == "hub_sources":
            return self._req("GET", "/v1/hub/sources")
        if op == "hub_source_add":
            return self._req("POST", "/v1/hub/sources", json=a)
        if op == "hub_source_archive":
            return self._req("DELETE", f"/v1/hub/sources/{_q(a['id'])}")
        if op == "hub_sensors":
            return self._req("GET", "/v1/hub/sensors", params=a)
        if op == "hub_sensor_add":
            return self._req("POST", "/v1/hub/sensors", json=a)
        if op == "hub_sensor_archive":
            return self._req("DELETE", f"/v1/hub/sensors/{_q(a['id'])}")
        if op == "hub_bindings":
            return self._req("GET", "/v1/hub/bindings", params=a)
        if op == "hub_binding_add":
            return self._req("POST", "/v1/hub/bindings", json=a)
        if op == "hub_binding_archive":
            return self._req("DELETE", f"/v1/hub/bindings/{_q(a['kind'])}/{_q(a['id'])}")
        if op == "hub_inbox":
            return self._req("GET", "/v1/hub/inbox", params=a)
        if op == "hub_inbox_resolve":
            return self._req(
                "POST",
                f"/v1/hub/inbox/{_q(a['id'])}:resolve",
                json={"action": a["action"], "node_id": a.get("node_id")},
            )
        if op == "hub_evaluate":
            return self._req("POST", "/v1/hub/evaluate", json=a)
        if op == "hub_reconcile":
            return self._req("POST", "/v1/hub/reconcile", json={})
        return {
            "ok": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"Unknown operation {op!r}",
                "hint": "",
                "details": {},
            },
        }

    def close(self) -> None:
        self.http.close()
