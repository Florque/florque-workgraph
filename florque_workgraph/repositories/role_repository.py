from typing import Any

from ..session import GraphManager
from ..queries.queries import (
    CREATE_ROLE,
    DELETE_ROLE,
    GET_ROLE,
    GET_ALL_ROLES,
    GET_WORKSPACE_ROLES,
    ADD_CAPABILITY_TO_ROLE,
    DELETE_HAS_CAPABILITY,
    GET_ROLE_CAPABILITIES,
    GET_CAPABILITY_ROLES,
    GET_ROLE_USERS,
)


class RoleRepository:
    """
    Workspace-scoped domain operations for Role nodes and their relationships.

    Roles are always bound to a workspace. Project-scoped roles additionally
    carry a project_id property; workspace-scoped roles do not.

    Every method automatically constrains queries to self.workspace_id so that
    no operation can cross tenant boundaries even when a direct node ID is given.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""
        return {"workspace_id": self.workspace_id, **kwargs}

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    def create(self, role_data: dict) -> list[Any]:
        """Create a Role node.

        role_data must contain: id, name, scope ("workspace"|"project").
        For project-scoped roles, also include project_id.
        workspace_id is always set from the repository context.
        """
        return self.db.execute_write(
            CREATE_ROLE,
            {**role_data, "workspace_id": self.workspace_id},
        )

    def get(self, role_id: str) -> list[Any]:
        """Return a single Role node by id, scoped to this workspace."""
        return self.db.execute(GET_ROLE, self._p(id=role_id))

    def get_all(self) -> list[Any]:
        """Return all Role nodes in this workspace (both scopes)."""
        return self.db.execute(GET_ALL_ROLES, self._p())

    def get_workspace_roles(self) -> list[Any]:
        """Return workspace-scoped Role nodes for this workspace."""
        return self.db.execute(GET_WORKSPACE_ROLES, self._p())

    def delete(self, role_id: str) -> None:
        """Detach-delete a Role node within this workspace."""
        self.db.execute_write(DELETE_ROLE, self._p(id=role_id))

    # ── Capabilities ──────────────────────────────────────────────────────────

    def add_capability(self, role_id: str, capability_id: str) -> None:
        """Grant a capability to this role."""
        self.db.execute_write(ADD_CAPABILITY_TO_ROLE, self._p(role_id=role_id, capability_id=capability_id))

    def remove_capability(self, role_id: str, capability_id: str) -> None:
        """Revoke a capability from this role."""
        self.db.execute_write(DELETE_HAS_CAPABILITY, self._p(role_id=role_id, capability_id=capability_id))

    def get_capabilities(self, role_id: str) -> list[Any]:
        """Return all Capability nodes granted to this role."""
        return self.db.execute(GET_ROLE_CAPABILITIES, self._p(role_id=role_id))

    def get_roles_with_capability(self, capability_id: str) -> list[Any]:
        """Return all Role nodes in this workspace that have the given capability."""
        return self.db.execute(GET_CAPABILITY_ROLES, self._p(capability_id=capability_id))

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_users(self, role_id: str) -> list[Any]:
        """Return all User nodes that hold this role."""
        return self.db.execute(GET_ROLE_USERS, self._p(role_id=role_id))
