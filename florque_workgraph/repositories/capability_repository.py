from typing import Any

from ..session import GraphManager
from ..queries import (
    CREATE_CAPABILITY,
    DELETE_CAPABILITY,
    GET_CAPABILITY,
    GET_ALL_CAPABILITIES,
    GET_CAPABILITY_ROLES,
)


class CapabilityRepository:
    """
    Global domain operations for Capability nodes.

    Capabilities are system-wide definitions (e.g. "ticket:create") and are not
    workspace-scoped. Roles within any workspace can reference them via
    HAS_CAPABILITY edges.
    """

    def __init__(self, db: GraphManager) -> None:
        self.db = db

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    def create(self, capability_data: dict) -> list[Any]:
        """Create a Capability node. capability_data must contain: id, name, description."""
        return self.db.execute_write(CREATE_CAPABILITY, capability_data)

    def get(self, capability_id: str) -> list[Any]:
        """Return a single Capability node by id."""
        return self.db.execute(GET_CAPABILITY, {"id": capability_id})

    def get_all(self) -> list[Any]:
        """Return all Capability nodes."""
        return self.db.execute(GET_ALL_CAPABILITIES)

    def delete(self, capability_id: str) -> None:
        """Detach-delete a Capability node and all its HAS_CAPABILITY edges."""
        self.db.execute_write(DELETE_CAPABILITY, {"id": capability_id})

    # ── Roles ─────────────────────────────────────────────────────────────────

    def get_roles_in_workspace(self, capability_id: str, workspace_id: str) -> list[Any]:
        """Return all Role nodes in the given workspace that have this capability."""
        return self.db.execute(GET_CAPABILITY_ROLES, {"capability_id": capability_id, "workspace_id": workspace_id})
