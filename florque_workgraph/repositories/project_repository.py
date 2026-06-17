from typing import Any

from ..session import GraphManager
from ..queries.queries import (
    CREATE_STRATEGY,
    DELETE_STRATEGY,
    GET_PROJECT_ROOT,
    GET_ALL_PROJECT_ROOTS,
    ADD_TICKET_TO_PROJECT_ROOT,
    REMOVE_TICKET_FROM_PROJECT_ROOT,
    GET_TICKETS_FOR_PROJECT_ROOT,
    UPDATE_STRATEGY,
)


class ProjectRootRepository:
    """
    Workspace-scoped domain operations for Project Root nodes and their relationships.
    A project root is a Strategy node with is_project = true.

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
        """Create a Project Root (Strategy node). project_data must contain: id, title, description, vision."""
        return self.db.execute_write(
            CREATE_STRATEGY, {**project_data, "workspace_id": self.workspace_id, "is_project": True, "archived": False}
        )

    def update(self, project_id: str, updates: dict) -> list[Any]:
        """Update fields on a Project Root (Strategy) node. `updates` may include title, description, vision."""
        params = {
            "id": project_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title", None),
            "description": updates.get("description", None),
            "vision": updates.get("vision", None),
            "is_project": True,
            "archived": None,
        }
        return self.db.execute_write(UPDATE_STRATEGY, params)

    def get(self, project_id: str) -> list[Any]:
        """Return a single Project Root node by id, scoped to this workspace."""
        return self.db.execute(GET_PROJECT_ROOT, self._p(id=project_id))

    def get_all(self) -> list[Any]:
        """Return all Project Root nodes in this workspace."""
        return self.db.execute(GET_ALL_PROJECT_ROOTS, self._p())

    def delete(self, project_id: str) -> None:
        """Detach-delete a Project Root node within this workspace."""
        self.db.execute_write(DELETE_STRATEGY, self._p(id=project_id))

    # ── Ticket membership ─────────────────────────────────────────────────────

    def add_ticket(self, ticket_id: str, project_id: str) -> None:
        """Create an INITIATES edge from a ticket to this project root."""
        self.db.execute_write(ADD_TICKET_TO_PROJECT_ROOT, self._p(ticket_id=ticket_id, strategy_id=project_id))

    def remove_ticket(self, ticket_id: str, project_id: str) -> None:
        """Remove the INITIATES edge from a ticket to this project root."""
        self.db.execute_write(REMOVE_TICKET_FROM_PROJECT_ROOT, self._p(ticket_id=ticket_id, strategy_id=project_id))

    def get_tickets(self, project_id: str, include_archived: bool = False) -> list[Any]:
        """Return all Ticket nodes that belong to this project root, within this workspace."""
        params = self._p(strategy_id=project_id, include_archived=include_archived)
        return self.db.execute(GET_TICKETS_FOR_PROJECT_ROOT, params)
