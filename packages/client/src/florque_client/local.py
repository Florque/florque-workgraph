"""In-process client: calls the core directly (local mode, single user, trust by convention)."""

from __future__ import annotations

from typing import Any

from florque_graph_core import Principal

from florque_client.app import FlorqueApp, build_app
from florque_client.base import Client
from florque_client.config import Config


def local_principal(cfg: Config) -> Principal:
    return Principal(
        actor_id=cfg.resolved_actor(),
        roles={"*": "admin"},
        is_agent=cfg.agent,
        can_create_projects=True,
    )


class LocalClient(Client):
    def __init__(self, app: FlorqueApp, principal: Principal) -> None:
        self.app = app
        self.principal = principal

    @classmethod
    def from_config(cls, cfg: Config) -> LocalClient:
        return cls(build_app(cfg), local_principal(cfg))

    def _call(self, op: str, **args: Any) -> dict[str, Any]:
        if op.startswith("auth_"):
            return {
                "ok": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Accounts exist only on the hosted service",
                    "hint": "Use --api-url with fwg register / fwg login (remote mode).",
                    "details": {},
                },
                "ontology_version": self.app.ontology_version,
            }
        return self.app.call(self.principal, op, **args)

    def close(self) -> None:
        self.app.close()
