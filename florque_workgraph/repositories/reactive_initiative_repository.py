from typing import Any
from ..session import GraphManager
from ..queries.reactive_initiative_queries import (
    CREATE_REACTIVE_INITIATIVE,
    GET_REACTIVE_INITIATIVE,
    UPDATE_REACTIVE_INITIATIVE,
    DELETE_REACTIVE_INITIATIVE,
    CREATE_REACTIVE_INITIATIVE_IN_PROJECT,
    GET_PROJECT_REACTIVE_INITIATIVES,
    GET_REACTIVE_INITIATIVE_TICKETS,
    DELETE_IN_PROJECT_BY_REACTIVE_INITIATIVE,
    SET_REACTIVE_INITIATIVE_ARCHIVED_STATUS,
    ADD_REACTIVE_INITIATIVE_TO_PROJECT,
)

class ReactiveInitiativeRepository:
    """
    Workspace-scoped domain operations for ReactiveInitiative nodes.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""
        return {"workspace_id": self.workspace_id, **kwargs}

    def create(self, initiative_data: dict) -> list[Any]:
        """Create a ReactiveInitiative node and atomically link it to a Project."""
        project_id = initiative_data.get("project_id")
        if not project_id:
            raise ValueError("project_id is required to create a ReactiveInitiative.")
            
        if "archived" not in initiative_data:
            initiative_data["archived"] = False
            
        return self.db.execute_write(CREATE_REACTIVE_INITIATIVE_IN_PROJECT, self._p(**initiative_data))


    def update(self, initiative_id: str, updates: dict) -> list[Any]:
        """Update a ReactiveInitiative node."""
        params = self._p(
            id=initiative_id,
            title=updates.get("title"),
            description=updates.get("description"),
            archived=updates.get("archived"),
        )

        rows = self.db.execute_write(UPDATE_REACTIVE_INITIATIVE, params)
        
        if "project_id" in updates:
            self.db.execute_write(DELETE_IN_PROJECT_BY_REACTIVE_INITIATIVE, self._p(reactive_initiative_id=initiative_id))
            new_proj_id = updates.get("project_id")
            if new_proj_id:
                self.db.execute_write(ADD_REACTIVE_INITIATIVE_TO_PROJECT, self._p(reactive_initiative_id=initiative_id, project_id=new_proj_id))
                    
        return rows

    def get(self, initiative_id: str) -> list[Any]:
        """Get a single ReactiveInitiative node."""
        return self.db.execute(GET_REACTIVE_INITIATIVE, self._p(id=initiative_id))

    def get_by_project(self, project_id: str, include_archived: bool = False) -> list[Any]:
        """Get all ReactiveInitiative nodes for a specific project."""
        return self.db.execute(GET_PROJECT_REACTIVE_INITIATIVES, self._p(project_id=project_id, include_archived=include_archived))

    def delete(self, initiative_id: str) -> None:
        """Delete a ReactiveInitiative node and its relationships."""
        self.db.execute_write(DELETE_REACTIVE_INITIATIVE, self._p(id=initiative_id))

    def get_tickets(self, initiative_id: str, include_archived: bool = False) -> list[Any]:
        """Get tickets that execute this ReactiveInitiative."""
        return self.db.execute(GET_REACTIVE_INITIATIVE_TICKETS, self._p(reactive_initiative_id=initiative_id, include_archived=include_archived))

    def set_archived_status(self, initiative_id: str, archived: bool) -> list[Any]:
        """Set the archived status of a ReactiveInitiative."""
        return self.db.execute_write(SET_REACTIVE_INITIATIVE_ARCHIVED_STATUS, self._p(id=initiative_id, archived=archived))
