from typing import Any
from ..session import GraphManager
from ..queries import (
    CREATE_STRATEGY,
    UPDATE_STRATEGY,
    DELETE_STRATEGY,
    GET_STRATEGY,
    GET_ALL_STRATEGIES,
    CREATE_PURSUES,
    DELETE_PURSUES,
    GET_STRATEGY_VISION,
    CREATE_TRACKS_VIA,
    DELETE_TRACKS_VIA,
    GET_STRATEGY_GOALS,
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

    def create(self, strategy_data: dict) -> list[Any]:
        """Create a Strategy node."""

        return self.db.execute_write(CREATE_STRATEGY, {**strategy_data, "workspace_id": self.workspace_id})

    def update(self, strategy_id: str, updates: dict) -> list[Any]:
        """Update a Strategy node."""
        params = {
            "id": strategy_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title"),
            "description": updates.get("description"),
        }

        return self.db.execute_write(UPDATE_STRATEGY, params)

    def get(self, strategy_id: str) -> list[Any]:
        """Get a single Strategy node."""

        return self.db.execute(GET_STRATEGY, self._p(id=strategy_id))

    def get_all(self) -> list[Any]:
        """Get all Strategy nodes in this workspace."""

        return self.db.execute(GET_ALL_STRATEGIES, self._p())

    def delete(self, strategy_id: str) -> None:
        """Delete a Strategy node."""
        self.db.execute_write(DELETE_STRATEGY, self._p(id=strategy_id))

    # Relationships
    def add_vision(self, strategy_id: str, vision_id: str) -> None:
        """Strategy PURSUES Vision."""
        self.db.execute_write(CREATE_PURSUES, self._p(strategy_id=strategy_id, vision_id=vision_id))

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

    def get_goals(self, strategy_id: str) -> list[Any]:
        """Get goals tracked via this strategy."""

        return self.db.execute(GET_STRATEGY_GOALS, self._p(strategy_id=strategy_id))
