from typing import Any
from ..session import GraphManager
from ..queries import (
    CREATE_VISION,
    UPDATE_VISION,
    DELETE_VISION,
    GET_VISION,
    GET_ALL_VISIONS,
    GET_VISION_STRATEGIES,
    CREATE_VISION_IN_PROJECT,
    DELETE_IN_PROJECT_BY_VISION,
    GET_PROJECT_VISIONS,
    SET_VISION_ARCHIVED_STATUS,
)

class VisionRepository:
    """
    Workspace-scoped domain operations for Vision nodes.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""

        return {"workspace_id": self.workspace_id, **kwargs}

    def create(self, vision_data: dict) -> list[Any]:
        """Create a Vision node."""
        
        project_id = vision_data.get("project_id")
        if not project_id:
            raise ValueError("project_id is required to create a Vision.")
            
        # Ensure 'archived' parameter is present, defaulting to False
        if "archived" not in vision_data:
            vision_data["archived"] = False
            
        rows = self.db.execute_write(CREATE_VISION, {**vision_data, "workspace_id": self.workspace_id})
        
        vision_id = vision_data.get("id")
        if vision_id:
            try:
                self.db.execute_write(CREATE_VISION_IN_PROJECT, {"vision_id": vision_id, "project_id": project_id, "workspace_id": self.workspace_id})
            except Exception:
                pass
                
        return rows

    def update(self, vision_id: str, updates: dict) -> list[Any]:
        """Update a Vision node."""
        params = {
            "id": vision_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title"),
            "description": updates.get("description"),
            "project_id": updates.get("project_id"),
            "archived": updates.get("archived"),
        }

        rows = self.db.execute_write(UPDATE_VISION, params)
        
        if "project_id" in updates:
            try:
                self.db.execute_write(DELETE_IN_PROJECT_BY_VISION, {"vision_id": vision_id, "workspace_id": self.workspace_id})
            except Exception:
                pass

            new_proj = updates.get("project_id")
            if new_proj:
                try:
                    self.db.execute_write(CREATE_VISION_IN_PROJECT, {"vision_id": vision_id, "project_id": new_proj, "workspace_id": self.workspace_id})
                except Exception:
                    pass
                    
        return rows

    def get(self, vision_id: str) -> list[Any]:
        """Get a single Vision node."""

        return self.db.execute(GET_VISION, self._p(id=vision_id))

    def get_all(self, include_archived: bool = False) -> list[Any]:
        """Get all Vision nodes in this workspace."""
        return self.db.execute(GET_ALL_VISIONS, self._p(include_archived=include_archived))

    def get_by_project(self, project_id: str, include_archived: bool = False) -> list[Any]:
        """Get all Vision nodes for a specific project in this workspace."""
        return self.db.execute(GET_PROJECT_VISIONS, self._p(project_id=project_id, include_archived=include_archived))

    def delete(self, vision_id: str) -> None:
        """Delete a Vision node."""
        strategies = self.get_strategies(vision_id)
        if strategies:
            raise ValueError(f"Cannot delete vision {vision_id} because it has associated strategies pursuing it.")
        self.db.execute_write(DELETE_VISION, self._p(id=vision_id))

    def get_strategies(self, vision_id: str, include_archived: bool = False) -> list[Any]:
        """Get strategies pursuing this vision."""
        return self.db.execute(GET_VISION_STRATEGIES, self._p(vision_id=vision_id, include_archived=include_archived))

    def set_archived_status(self, vision_id: str, archived: bool) -> list[Any]:
        """Set the archived status of a vision."""
        return self.db.execute_write(
            SET_VISION_ARCHIVED_STATUS, self._p(vision_id=vision_id, archived=archived)
        )
