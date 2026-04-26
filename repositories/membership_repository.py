from typing import Any, Optional

from ..session import GraphManager
from ..queries import (
    CREATE_MEMBERSHIP,
    DELETE_MEMBERSHIP,
    GET_MEMBERSHIP,
    GET_MEMBERSHIP_BY_USER_WORKSPACE,
    GET_PENDING_INVITATIONS,
    GET_WORKSPACE,
    GET_USER,
    CREATE_HAS_MEMBERSHIP,
    CREATE_MEMBERSHIP_IN_WORKSPACE,
    CREATE_MEMBERSHIP_HAS_ROLE,
    DELETE_MEMBERSHIP_HAS_ROLE,
    GET_MEMBERSHIP_ROLES,
)


class MembershipRepository:
    """
    Domain operations for Membership nodes that bridge Users and Workspaces.
    A Membership is unique per (user, workspace) pair and holds role assignments.
    """

    def __init__(self, db: GraphManager) -> None:
        self.db = db

    def _membership_id(self, user_id: Optional[str], workspace_id: str, provided: Optional[str] = None) -> str:
        """Deterministically derive membership id when not provided."""
        if provided:
            return provided
        if user_id:
            return f"{user_id}:{workspace_id}"
        
        # For detached memberships, we need a unique ID to avoid collisions
        import uuid
        return f"detached_{uuid.uuid4().hex[:8]}:{workspace_id}"

    # ── Node CRUD ──────────────────────────────────────────────────────────────
    # If user_id is None, creates a detached membership that can later be linked to a user when they sign up with the same email.
    # This allows for pre-creating memberships for invited users who haven't signed up yet.
    def create(self, user_id: Optional[str], workspace_id: str, email: Optional[str] = None, membership_id: Optional[str] = None) -> list[Any]:
        """
        Create a Membership node and wire it to the User and Workspace.
        Workspace must already exist; User is global. If user_id is None, it creates a detached membership using email.
        """
        # Ensure workspace exists to avoid isolated membership
        workspace = self.db.execute(GET_WORKSPACE, {"id": workspace_id})
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found; cannot create membership.")
        
        # Create membership node
        mid = self._membership_id(user_id, workspace_id, membership_id)
        membership_props = {"id": mid, "user_id": user_id, "workspace_id": workspace_id, "email": email}
        rows = self.db.execute_write(CREATE_MEMBERSHIP, membership_props)
        
        # Linking membership to user if user_id is provided
        if user_id:
            self.db.execute_write(CREATE_HAS_MEMBERSHIP, {"user_id": user_id, "membership_id": mid, "workspace_id": workspace_id})
        
        # Linking membership to workspace (always)
        self.db.execute_write(CREATE_MEMBERSHIP_IN_WORKSPACE, {"membership_id": mid, "workspace_id": workspace_id})
        
        return rows
    
    def get_pending_invitations(self, workspace_id: str) -> list[Any]:
        """Get all pending invitations (emails) for a workspace."""
        return self.db.execute(GET_PENDING_INVITATIONS, {"workspace_id": workspace_id})  

    def get(self, membership_id: str) -> list[Any]:
        """Get membership by id."""
        return self.db.execute(GET_MEMBERSHIP, {"id": membership_id})

    def get_by_user_workspace(self, user_id: str, workspace_id: str) -> list[Any]:
        """Get membership by user/workspace pair."""
        return self.db.execute(GET_MEMBERSHIP_BY_USER_WORKSPACE, {"user_id": user_id, "workspace_id": workspace_id})

    def delete(self, membership_id: str) -> None:
        """Detach-delete membership."""
        self.db.execute_write(DELETE_MEMBERSHIP, {"id": membership_id})

    # ── Roles ─────────────────────────────────────────────────────────────────

    def add_role(self, membership_id: str, role_id: str, workspace_id: str) -> None:
        """Attach role to membership."""
        self.db.execute_write(
            CREATE_MEMBERSHIP_HAS_ROLE, {"membership_id": membership_id, "role_id": role_id, "workspace_id": workspace_id}
        )

    def remove_role(self, membership_id: str, role_id: str, workspace_id: str) -> None:
        """Detach role from membership."""
        self.db.execute_write(
            DELETE_MEMBERSHIP_HAS_ROLE, {"membership_id": membership_id, "role_id": role_id, "workspace_id": workspace_id}
        )

    def get_roles(self, membership_id: str, workspace_id: str) -> list[Any]:
        """Return roles for membership."""
        return self.db.execute(GET_MEMBERSHIP_ROLES, {"membership_id": membership_id, "workspace_id": workspace_id})
