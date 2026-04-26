from typing import Any

from ..session import GraphManager
from ..queries import (
    CREATE_PROJECT,
    DELETE_PROJECT,
    GET_PROJECT,
    GET_ALL_PROJECTS,
    CREATE_IN_WORKSPACE,
    DELETE_IN_WORKSPACE,
    CREATE_IN_PROJECT,
    DELETE_IN_PROJECT,
    GET_TICKETS_FOR_PROJECT,
    UPDATE_PROJECT,
)


class ProjectRepository:
    """
    Workspace-scoped domain operations for Project nodes and their relationships.

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

    def create(self, project_data: dict) -> list[Any]:
        """Create a Project node. project_data must contain: id, name, description.
        workspace_id is always set from the repository context."""
        return self.db.execute_write(CREATE_PROJECT, {**project_data, "workspace_id": self.workspace_id})

    def update(self, project_id: str, updates: dict) -> list[Any]:
        """Update fields on a Project node. `updates` may include name, description.

        Memgraph requires referenced parameters to be present even when NULL, so ensure
        all expected params exist (set to None when not provided).
        """
        params = {
            "id": project_id,
            "workspace_id": self.workspace_id,
            "name": updates.get("name", None),
            "description": updates.get("description", None),
        }
        return self.db.execute_write(UPDATE_PROJECT, params)

    def get(self, project_id: str) -> list[Any]:
        """Return a single Project node by id, scoped to this workspace."""
        return self.db.execute(GET_PROJECT, self._p(id=project_id))

    def get_all(self) -> list[Any]:
        """Return all Project nodes in this workspace."""
        return self.db.execute(GET_ALL_PROJECTS, self._p())

    def delete(self, project_id: str) -> None:
        """Detach-delete a Project node within this workspace."""
        self.db.execute_write(DELETE_PROJECT, self._p(id=project_id))

    # ── Workspace membership ──────────────────────────────────────────────────

    def add_to_workspace(self, project_id: str) -> None:
        """Create an IN_WORKSPACE edge from this project to its workspace."""
        self.db.execute_write(CREATE_IN_WORKSPACE, self._p(project_id=project_id))

    def remove_from_workspace(self, project_id: str) -> None:
        """Remove the IN_WORKSPACE edge from this project to its workspace."""
        self.db.execute_write(DELETE_IN_WORKSPACE, self._p(project_id=project_id))

    # ── Ticket membership ─────────────────────────────────────────────────────

    def add_ticket(self, ticket_id: str, project_id: str) -> None:
        """Create an IN_PROJECT edge from a ticket to this project."""
        self.db.execute_write(CREATE_IN_PROJECT, self._p(ticket_id=ticket_id, project_id=project_id))

    def remove_ticket(self, ticket_id: str, project_id: str) -> None:
        """Remove the IN_PROJECT edge from a ticket to this project."""
        self.db.execute_write(DELETE_IN_PROJECT, self._p(ticket_id=ticket_id, project_id=project_id))

    def get_tickets(self, project_id: str) -> list[Any]:
        """Return all Ticket nodes that belong to this project, within this workspace."""
        return self.db.execute(GET_TICKETS_FOR_PROJECT, self._p(project_id=project_id))
