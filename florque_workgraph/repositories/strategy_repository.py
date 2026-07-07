from typing import Any
from ..session import GraphManager
from ..queries.queries import (
    CREATE_STRATEGY,
    UPDATE_STRATEGY,
    DELETE_STRATEGY,
    GET_STRATEGY,
    GET_ALL_STRATEGIES,
    CREATE_TRACKS_VIA,
    DELETE_TRACKS_VIA,
    GET_STRATEGY_GOALS,
    SET_STRATEGY_ARCHIVED_STATUS,
    REMOVE_TICKET_FROM_STRATEGY,
    GET_TICKETS_FOR_STRATEGY,
    GET_STRATEGY_WORKGRAPH,
    GET_TICKETS_REQUIRING_STRATEGY,
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
        params = self._p(**strategy_data)
        params.setdefault("archived", None)
        params.setdefault("is_project", None)
        return self.db.execute_write(CREATE_STRATEGY, params)

    def update(self, strategy_id: str, updates: dict) -> list[Any]:
        """Update a Strategy node."""
        params = {
            "id": strategy_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title"),
            "description": updates.get("description"),
            "is_project": updates.get("is_project"),
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

    def add_goal(self, strategy_id: str, goal_id: str) -> None:
        """Strategy TRACKS_VIA Goal."""
        self.db.execute_write(CREATE_TRACKS_VIA, self._p(strategy_id=strategy_id, goal_id=goal_id))

    def remove_goal(self, strategy_id: str, goal_id: str) -> None:
        """Remove Strategy TRACKS_VIA Goal."""
        self.db.execute_write(DELETE_TRACKS_VIA, self._p(strategy_id=strategy_id, goal_id=goal_id))

    def get_goals(self, strategy_id: str, include_archived: bool = False) -> list[Any]:
        """Get goals tracked via this strategy."""
        return self.db.execute(GET_STRATEGY_GOALS, self._p(strategy_id=strategy_id, include_archived=include_archived))
    
    # Tickets

    def remove_ticket(self, strategy_id: str, ticket_id: str) -> None:
        """Remove Ticket REQUIRES_STRATEGY Strategy."""
        self.db.execute_write(REMOVE_TICKET_FROM_STRATEGY, self._p(strategy_id=strategy_id, ticket_id=ticket_id))

    def get_tickets(self, strategy_id: str) -> list[Any]:
        """Get tickets that require this strategy."""
        tickets = self.db.execute(GET_TICKETS_FOR_STRATEGY, self._p(strategy_id=strategy_id))
        for ticket in tickets:
            ticket_node = ticket[0]
            is_initiative = ticket[1] if len(ticket) > 1 else False
            if hasattr(ticket_node, "properties") and isinstance(ticket_node.properties, dict):
                ticket_node.properties['is_initiative'] = is_initiative
            elif isinstance(ticket_node, dict):
                ticket_node['is_initiative'] = is_initiative
        return tickets

    # Strategy status

    def set_archived_status(self, strategy_id: str, archived: bool) -> list[Any]:
        """Set the archived status of a strategy."""
        return self.db.execute_write(
            SET_STRATEGY_ARCHIVED_STATUS, self._p(strategy_id=strategy_id, archived=archived)
        )
        
    # Get the full downstream workgraph for a strategy

    def get_strategy_workgraph(self, strategy_id: str) -> list[Any]:
        """Get the full downstream workgraph for a strategy."""
        return self.db.execute(GET_STRATEGY_WORKGRAPH, self._p(strategy_id=strategy_id))

    def get_requiring_tickets(self, strategy_id: str) -> list[Any]:
        """Get tickets that require this strategy."""
        return self.db.execute(GET_TICKETS_REQUIRING_STRATEGY, self._p(strategy_id=strategy_id))
