from typing import Any
from ..session import GraphManager
from ..queries.queries import (
    CREATE_STRATEGY_PURSUES_VISION,
    UPDATE_STRATEGY,
    DELETE_STRATEGY,
    GET_STRATEGY,
    GET_ALL_STRATEGIES,

    DELETE_PURSUES,
    GET_STRATEGY_VISION,
    CREATE_TRACKS_VIA,
    DELETE_TRACKS_VIA,
    GET_STRATEGY_GOALS,
    SET_STRATEGY_ARCHIVED_STATUS,
)

class StrategyRepository:
    """
    Workspace-scoped domain operations for Strategy nodes.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""

        return {"workspace_id": self.workspace_id, **kwargs}

    def create(self, strategy_data: dict, vision_id: str) -> list[Any]:
        """Create a Strategy node and connect it to a Vision."""
        if "archived" not in strategy_data:
            strategy_data["archived"] = False
        params = {**strategy_data, "vision_id": vision_id, "workspace_id": self.workspace_id}
        return self.db.execute_write(CREATE_STRATEGY_PURSUES_VISION, params)

    def update(self, strategy_id: str, updates: dict) -> list[Any]:
        """Update a Strategy node."""
        params = {
            "id": strategy_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title"),
            "description": updates.get("description"),
            "archived": updates.get("archived"),
        }

        return self.db.execute_write(UPDATE_STRATEGY, params)

    def get(self, strategy_id: str) -> list[Any]:
        """Get a single Strategy node."""

        return self.db.execute(GET_STRATEGY, self._p(id=strategy_id))

    def get_all(self, include_archived: bool = False) -> list[Any]:
        """Get all Strategy nodes in this workspace."""
        return self.db.execute(GET_ALL_STRATEGIES, self._p(include_archived=include_archived))

    def delete(self, strategy_id: str) -> None:
        """Delete a Strategy node."""
        goals = self.get_goals(strategy_id)
        if goals:
            raise ValueError(f"Cannot delete strategy {strategy_id} because it has associated goals tracked via it.")
        self.db.execute_write(DELETE_STRATEGY, self._p(id=strategy_id))

    # Relationships

    def remove_vision(self, strategy_id: str, vision_id: str) -> None:
        """Remove Strategy PURSUES Vision."""
        self.db.execute_write(DELETE_PURSUES, self._p(strategy_id=strategy_id, vision_id=vision_id))

    def get_vision(self, strategy_id: str) -> list[Any]:
        """Get vision pursued by this strategy."""

        return self.db.execute(GET_STRATEGY_VISION, self._p(strategy_id=strategy_id))

    def add_goal(self, strategy_id: str, goal_id: str) -> None:
        """Strategy TRACKS_VIA Goal."""
        self.db.execute_write(CREATE_TRACKS_VIA, self._p(strategy_id=strategy_id, goal_id=goal_id))

    def remove_goal(self, strategy_id: str, goal_id: str) -> None:
        """Remove Strategy TRACKS_VIA Goal."""
        self.db.execute_write(DELETE_TRACKS_VIA, self._p(strategy_id=strategy_id, goal_id=goal_id))

    def get_goals(self, strategy_id: str, include_archived: bool = False) -> list[Any]:
        """Get goals tracked via this strategy."""
        return self.db.execute(GET_STRATEGY_GOALS, self._p(strategy_id=strategy_id, include_archived=include_archived))

    def set_archived_status(self, strategy_id: str, archived: bool) -> list[Any]:
        """Set the archived status of a strategy."""
        return self.db.execute_write(
            SET_STRATEGY_ARCHIVED_STATUS, self._p(strategy_id=strategy_id, archived=archived)
        )
