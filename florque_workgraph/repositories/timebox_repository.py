from typing import Any

from ..session import GraphManager
from ..queries import (
    CREATE_TIMEBOX,
    DELETE_TIMEBOX,
    GET_TIMEBOX,
    GET_ALL_TIMEBOXES,
    CREATE_SCHEDULED,
    GET_SCHEDULED_TICKETS,
    GET_ALL_TICKETS_FOR_TIMEBOX,
)


class TimeboxRepository:
    """
    Workspace-scoped domain operations for Timebox nodes.

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

    def create(self, timebox_data: dict) -> list[Any]:
        """Create a Timebox node. timebox_data must contain: id, name, start_date, end_date, status.
        workspace_id is always set from the repository context."""
        return self.db.execute_write(CREATE_TIMEBOX, {**timebox_data, "workspace_id": self.workspace_id})

    def get(self, timebox_id: str) -> list[Any]:
        """Return a single Timebox node by id, scoped to this workspace."""
        return self.db.execute(GET_TIMEBOX, self._p(id=timebox_id))

    def get_all(self) -> list[Any]:
        """Return all Timebox nodes in this workspace."""
        return self.db.execute(GET_ALL_TIMEBOXES, self._p())

    def delete(self, timebox_id: str) -> None:
        """Detach-delete a Timebox node within this workspace."""
        self.db.execute_write(DELETE_TIMEBOX, self._p(id=timebox_id))

    # ── Scheduling ────────────────────────────────────────────────────────────

    def schedule_ticket(self, ticket_id: str, timebox_id: str) -> None:
        self.db.execute_write(CREATE_SCHEDULED, self._p(ticket_id=ticket_id, timebox_id=timebox_id))

    def get_scheduled_tickets(self, timebox_id: str) -> list[Any]:
        """Return Ticket nodes directly linked to this timebox, within this workspace."""
        return self.db.execute(GET_SCHEDULED_TICKETS, self._p(timebox_id=timebox_id))

    def get_tickets(self, timebox_id: str) -> list[Any]:
        """Return all Ticket nodes scheduled in this timebox, within this workspace."""
        return self.db.execute(GET_ALL_TICKETS_FOR_TIMEBOX, self._p(timebox_id=timebox_id))
