from typing import Any

from ..session import GraphManager
from ..queries import (
    CREATE_USER,
    UPDATE_USER,
    DELETE_USER,
    GET_USER,
    GET_USER_BY_EMAIL,
    GET_WORKSPACE_USERS,
    CREATE_ASSIGNED,
    DELETE_ASSIGNED,
    CREATE_CREATED,
    GET_ALL_TICKETS_FOR_ASSIGNEE,
    GET_CREATED_TICKETS,
    CREATE_MEMBERSHIP_HAS_ROLE,
    DELETE_MEMBERSHIP_HAS_ROLE,
    GET_MEMBERSHIP_ROLES,
)
from .membership_repository import MembershipRepository
from typing import Any, Optional


class UserRepository:
    """
    Domain operations for User nodes.

    Users are global (not workspace-scoped), but any method that touches Ticket
    nodes requires an explicit workspace_id to enforce tenant isolation.
    """

    def __init__(self, db: GraphManager) -> None:
        self.db = db

    def _row_to_dict(self, row: Any) -> dict:
        node = row[0]
        return dict(node.properties)

    def _ensure_membership(self, user_id: str, workspace_id: str) -> str:
        """Ensure membership exists for user/workspace; create if missing. Returns membership id."""
        membership_repo = MembershipRepository(self.db)
        existing = membership_repo.get_by_user_workspace(user_id, workspace_id)
        if existing:
            return self._row_to_dict(existing[0])["id"]
        created = membership_repo.create(user_id, workspace_id)
        return self._row_to_dict(created[0])["id"]

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    def create(self, user_data: dict) -> list[Any]:
        """Create a User node. user_data must contain: id, name, email."""
        return self.db.execute_write(CREATE_USER, user_data)

    def update(self, user_id: str, user_data: dict) -> list[Any]:
        """Update a User node's properties. user_data can contain: name, email."""
        
        existing = self.db.execute(GET_USER, {"id": user_id})
        if not existing:
            raise ValueError(f"User {user_id} not found; cannot update.")
        
        # Merge existing properties with updates
        existing_props = self._row_to_dict(existing[0])
        updated_props = {**existing_props, **user_data}
        
        return self.db.execute_write(UPDATE_USER, {"id": user_id, **updated_props})  # Using UPDATE_USER for upsert behavior

    def get(self, user_id: str) -> list[Any]:
        """Return a single User node by id."""
        return self.db.execute(GET_USER, {"id": user_id})

    def get_by_email(self, email: str) -> list[Any]:
        """Return a single User node by email."""
        return self.db.execute(GET_USER_BY_EMAIL, {"email": email})

    def get_workspace_users(self, workspace_id: str) -> list[Any]:
        """Return all User nodes that have a membership in the given workspace."""
        return self.db.execute(GET_WORKSPACE_USERS, {"workspace_id": workspace_id})

    def delete(self, user_id: str) -> None:
        """Detach-delete a User node and all its relationships."""
        self.db.execute_write(DELETE_USER, {"id": user_id})

    # ── Ticket relationships (workspace-scoped) ────────────────────────────────

    def assign_to_ticket(self, user_id: str, ticket_id: str, workspace_id: str) -> None:
        self.db.execute_write(CREATE_ASSIGNED, {"user_id": user_id, "ticket_id": ticket_id, "workspace_id": workspace_id})

    def unassign_from_ticket(self, user_id: str, ticket_id: str, workspace_id: str) -> None:
        self.db.execute_write(DELETE_ASSIGNED, {"user_id": user_id, "ticket_id": ticket_id, "workspace_id": workspace_id})

    def get_assigned_tickets(self, user_id: str, workspace_id: str) -> list[Any]:
        """Return all Ticket nodes assigned to this user within the given workspace."""
        return self.db.execute(GET_ALL_TICKETS_FOR_ASSIGNEE, {"user_id": user_id, "workspace_id": workspace_id})

    def set_ticket_creator(self, user_id: str, ticket_id: str, workspace_id: str) -> None:
        self.db.execute_write(CREATE_CREATED, {"user_id": user_id, "ticket_id": ticket_id, "workspace_id": workspace_id})

    def get_created_tickets(self, user_id: str, workspace_id: str) -> list[Any]:
        """Return all Ticket nodes created by this user within the given workspace."""
        return self.db.execute(GET_CREATED_TICKETS, {"user_id": user_id, "workspace_id": workspace_id})

    # ── Roles (workspace-scoped) ───────────────────────────────────────────────

    def assign_role(self, user_id: str, role_id: str, workspace_id: str) -> None:
        """Grant a role to a user within the given workspace via membership."""
        membership_id = self._ensure_membership(user_id, workspace_id)
        self.db.execute_write(
            CREATE_MEMBERSHIP_HAS_ROLE, {"membership_id": membership_id, "role_id": role_id, "workspace_id": workspace_id}
        )

    def revoke_role(self, user_id: str, role_id: str, workspace_id: str) -> None:
        """Revoke a role from a user within the given workspace."""
        membership_id = self._ensure_membership(user_id, workspace_id)
        self.db.execute_write(
            DELETE_MEMBERSHIP_HAS_ROLE,
            {"membership_id": membership_id, "role_id": role_id, "workspace_id": workspace_id},
        )

    def get_roles(self, user_id: str, workspace_id: str) -> list[Any]:
        """Return all Role nodes held by this user within the given workspace."""
        membership_id = self._ensure_membership(user_id, workspace_id)
        return self.db.execute(GET_MEMBERSHIP_ROLES, {"membership_id": membership_id, "workspace_id": workspace_id})
