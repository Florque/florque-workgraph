from typing import Any
from ..session import GraphManager
from ..queries import (
    CREATE_GOAL,
    UPDATE_GOAL,
    DELETE_GOAL,
    GET_GOAL,
    GET_ALL_GOALS,
    GET_GOAL_STRATEGY,
    GET_GOAL_TICKETS,
    SET_GOAL_ARCHIVED_STATUS,
    CREATE_GOAL_TRACKING_STRATEGY,
)

class GoalRepository:
    """
    Workspace-scoped domain operations for Goal nodes.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""

        return {"workspace_id": self.workspace_id, **kwargs}

    def create(self, goal_data: dict, strategy_id: str) -> list[Any]:
        """Create a Goal node and connect it to a Strategy."""
        if "archived" not in goal_data:
            goal_data["archived"] = False
        params = {**goal_data, "strategy_id": strategy_id, "workspace_id": self.workspace_id}
        return self.db.execute_write(CREATE_GOAL_TRACKING_STRATEGY, params)

    def update(self, goal_id: str, updates: dict) -> list[Any]:
        """Update a Goal node."""
        params = {
            "id": goal_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title"),
            "description": updates.get("description"),
            "archived": updates.get("archived"),
        }

        return self.db.execute_write(UPDATE_GOAL, params)

    def get(self, goal_id: str) -> list[Any]:
        """Get a single Goal node."""

        return self.db.execute(GET_GOAL, self._p(id=goal_id))

    def get_all(self, include_archived: bool = False) -> list[Any]:
        """Get all Goal nodes in this workspace."""
        return self.db.execute(GET_ALL_GOALS, self._p(include_archived=include_archived))

    def delete(self, goal_id: str) -> None:
        """Delete a Goal node."""
        tickets = self.get_tickets(goal_id)
        if tickets:
            raise ValueError(f"Cannot delete goal {goal_id} because it has associated tickets executing it.")
        self.db.execute_write(DELETE_GOAL, self._p(id=goal_id))

    def get_strategy(self, goal_id: str) -> list[Any]:
        """Get strategy tracking via this goal."""

        return self.db.execute(GET_GOAL_STRATEGY, self._p(goal_id=goal_id))

    def get_tickets(self, goal_id: str) -> list[Any]:
        """Get tickets executing this goal."""

        return self.db.execute(GET_GOAL_TICKETS, self._p(goal_id=goal_id))

    def set_archived_status(self, goal_id: str, archived: bool) -> list[Any]:
        """Set the archived status of a goal."""
        return self.db.execute_write(
            SET_GOAL_ARCHIVED_STATUS, self._p(goal_id=goal_id, archived=archived)
        )
