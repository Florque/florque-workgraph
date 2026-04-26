from typing import Any, Optional

from uuid_utils import uuid4

from ..session import GraphManager
from ..queries import (
    CREATE_WORKSPACE,
    DELETE_WORKSPACE,
    GET_WORKSPACE,
    GET_USER_WORKSPACES,
    GET_PROJECTS_FOR_WORKSPACE,
    GET_TICKETS_FOR_WORKSPACE,
    CREATE_ROLE,
    CREATE_HAS_CAPABILITY,
    LINK_DETACHED_MEMBERSHIPS,
)
from .user_repository import UserRepository
from .membership_repository import MembershipRepository
from .capability_repository import CapabilityRepository


class WorkspaceRepository:
    """Domain operations for Workspace nodes."""

    def __init__(self, db: GraphManager) -> None:
        self.db = db

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    def create(self, workspace_data: dict) -> list[Any]:
        """Create a Workspace node and bootstrap creator membership + admin role.
        workspace_data must contain: id, name, creator_user_id.
        """
        if "creator_user_id" not in workspace_data:
            raise ValueError("creator_user_id is required to create a workspace")

        # 1. Create the workspace node
        workspace_props = {"id": workspace_data["id"], "name": workspace_data["name"]}
        result = self.db.execute_write(CREATE_WORKSPACE, workspace_props)
        workspace_id = workspace_props["id"]
        creator_user_id = workspace_data["creator_user_id"]

        # 2. Ensure user node exists.
        #Fallback logic: if the user doesn't exist, create a new user with the provided creator_user_id as both id and name.
        user_repository = UserRepository(self.db)
        user_rows = user_repository.get(creator_user_id)
        
        if not user_rows:
            from sql_db.db_auth_manager import (get_user_by_id)
            try:
                user_data = get_user_by_id(int(creator_user_id))
            except (ValueError, TypeError):
                user_data = None
            name = getattr(user_data, "name", "NA") if user_data else "NA"
            email = getattr(user_data, "email", "NA") if user_data else "NA"

            user_repository.create({
                "id": creator_user_id,
                "name": name,
                "email": email
            })
        
        # 3. Ensure membership for creator in this workspace
        membership_repo = MembershipRepository(self.db)
        membership_rows = membership_repo.create(creator_user_id, workspace_id)
        membership_id = membership_rows[0][0].properties["id"]

        # 4. Create Admin role for this workspace
        from uuid import uuid4

        role_id = str(uuid4())
        role_data = {
            "id": role_id,
            "name": "Admin",
            "scope": "workspace",
            "workspace_id": workspace_id,
            "project_id": None,
        }
        self.db.execute_write(CREATE_ROLE, role_data)

        # 5. Link membership to Admin role
        membership_repo.add_role(membership_id, role_id, workspace_id)

        # 6. Grant all capabilities to Admin role
        capabilities_repo = CapabilityRepository(self.db)
        capabilities = capabilities_repo.get_all()
        for row in capabilities:
            cap_id = row[0].properties["id"]
            self.db.execute_write(
                CREATE_HAS_CAPABILITY, {"role_id": role_id, "capability_id": cap_id, "workspace_id": workspace_id}
            )

        return result

    def get(self, workspace_id: str) -> list[Any]:
        """Return a single Workspace node by id."""
        return self.db.execute(GET_WORKSPACE, {"id": workspace_id})

    def get_user_workspaces(self, user_id: str, email: Optional[str] = None) -> list[Any]:
        """Return all Workspace nodes where the user is a member. 
        Automatically links any detached memberships associated with the provided email.
        """
        
        if not email:
            from sql_db.db_auth_manager import get_user_by_id
            
            try:
                user = get_user_by_id(int(user_id))
                email = getattr(user, "email", None)
            except (ValueError, TypeError):
                email = None
            
            if email:
                user_repository = UserRepository(self.db)
                user_repository.update(user_id, {"email": email} if email else {})
        
        if email:
            self.db.execute_write(LINK_DETACHED_MEMBERSHIPS, {"user_id": user_id, "email": email})
            
        return self.db.execute(GET_USER_WORKSPACES, {"user_id": user_id})

    def delete(self, workspace_id: str) -> None:
        """Detach-delete a Workspace node and all its relationships."""
        self.db.execute_write(DELETE_WORKSPACE, {"id": workspace_id})

    # ── Scoped getters ────────────────────────────────────────────────────────

    def get_projects(self, workspace_id: str) -> list[Any]:
        """Return all Project nodes that belong to this workspace."""
        return self.db.execute(GET_PROJECTS_FOR_WORKSPACE, {"workspace_id": workspace_id})

    def get_tickets(self, workspace_id: str) -> list[Any]:
        """Return all Ticket nodes that belong to this workspace."""
        return self.db.execute(GET_TICKETS_FOR_WORKSPACE, {"workspace_id": workspace_id})
