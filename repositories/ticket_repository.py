from typing import Any

from ..session import GraphManager
from ..queries import (
    CREATE_TICKET,
    DELETE_TICKET,
    GET_TICKET,
    GET_ALL_TICKETS,
    CREATE_IN_PROJECT,
    CREATE_SUBTASK,
    DELETE_SUBTASK,
    GET_SUBTASKS,
    GET_PARENT_TICKETS,
    CREATE_DEPEND_ON,
    DELETE_DEPEND_ON,
    GET_DEPENDENCIES,
    GET_DEPENDENTS,
    CREATE_RELATES_TO,
    DELETE_RELATES_TO,
    GET_RELATED,
    CREATE_ASSIGNED,
    DELETE_ASSIGNED,
    GET_ASSIGNED_USERS,
    CREATE_CREATED,
    GET_CREATOR,
    CREATE_SCHEDULED,
    GET_SCHEDULED_TIMEBOX,
    GET_ALL_SUBTICKETS_FOR_TICKET,
    GET_TICKET_EDGES_BY_TYPE,
    UPDATE_TICKET,
    DELETE_IN_PROJECT_BY_TICKET,
    CREATE_EXECUTES,
    DELETE_EXECUTES,
    GET_TICKET_GOALS,
)


class TicketRepository:
    """
    Workspace-scoped domain operations for Ticket nodes and their relationships.

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

    def create(self, ticket_data: dict) -> list[Any]:
        """Create a Ticket node. ticket_data must contain: id, title, description, status, project_id.
        workspace_id is always set from the repository context."""
        params = {**ticket_data, "workspace_id": self.workspace_id}
        rows = self.db.execute_write(CREATE_TICKET, params)

        # If a project_id was provided, also ensure the IN_PROJECT relationship exists.
        project_id = ticket_data.get("project_id")
        ticket_id = ticket_data.get("id")
        if project_id and ticket_id:
            try:
                self.db.execute_write(CREATE_IN_PROJECT, {"ticket_id": ticket_id, "project_id": project_id, "workspace_id": self.workspace_id})
            except Exception:
                # Relationship creation failure shouldn't break node creation; log if needed upstream.
                pass
        
        parent_ticket_id = ticket_data.get("parent_id")
        
        if parent_ticket_id:
            try:
                self.db.execute_write(CREATE_SUBTASK, {"parent_id": parent_ticket_id, "child_id": ticket_id, "workspace_id": self.workspace_id})
            except Exception:
                pass

        return rows

    def update(self, ticket_id: str, updates: dict) -> list[Any]:
        """Update fields on a Ticket node. `updates` may include title, description, status, project_id.

        Memgraph requires referenced parameters to be present even when NULL, so ensure
        all expected params exist (set to None when not provided).
        """
        params = {
            "id": ticket_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title", None),
            "description": updates.get("description", None),
            "status": updates.get("status", None),
            "project_id": updates.get("project_id", None),
        }
        rows = self.db.execute_write(UPDATE_TICKET, params)

        # If project_id explicitly provided in updates, adjust IN_PROJECT relations
        if "project_id" in updates:
            # remove any existing IN_PROJECT rels for this ticket
            try:
                self.db.execute_write(DELETE_IN_PROJECT_BY_TICKET, {"ticket_id": ticket_id, "workspace_id": self.workspace_id})
            except Exception:
                pass

            # create new IN_PROJECT relation if project_id is not null/empty
            new_proj = updates.get("project_id")
            if new_proj:
                try:
                    self.db.execute_write(CREATE_IN_PROJECT, {"ticket_id": ticket_id, "project_id": new_proj, "workspace_id": self.workspace_id})
                except Exception:
                    pass

        return rows

    def get(self, ticket_id: str) -> list[Any]:
        """Return a single Ticket node by id, scoped to this workspace."""
        return self.db.execute(GET_TICKET, self._p(id=ticket_id))

    def get_all(self) -> list[Any]:
        """Return all Ticket nodes in this workspace."""
        return self.db.execute(GET_ALL_TICKETS, self._p())

    def delete(self, ticket_id: str) -> None:
        """Detach-delete a Ticket node within this workspace."""
        self.db.execute_write(DELETE_TICKET, self._p(id=ticket_id))

    # ── Hierarchy ──────────────────────────────────────────────────────────────

    def add_subtask(self, parent_id: str, child_id: str) -> None:
        self.db.execute_write(CREATE_SUBTASK, self._p(parent_id=parent_id, child_id=child_id))

    def remove_subtask(self, parent_id: str, child_id: str) -> None:
        self.db.execute_write(DELETE_SUBTASK, self._p(parent_id=parent_id, child_id=child_id))

    def get_subtasks(self, parent_id: str) -> list[Any]:
        """Return direct child Ticket nodes within this workspace."""
        return self.db.execute(GET_SUBTASKS, self._p(parent_id=parent_id))

    def get_parent_tickets(self, child_id: str) -> list[Any]:
        """Return direct parent Ticket nodes within this workspace."""
        return self.db.execute(GET_PARENT_TICKETS, self._p(child_id=child_id))

    def get_all_subtickets(self, ticket_id: str) -> list[Any]:
        """Return all descendant Ticket nodes (recursive via SUBTASK) within this workspace."""
        return self.db.execute(GET_ALL_SUBTICKETS_FOR_TICKET, self._p(ticket_id=ticket_id))

    def get_edges_by_type(self, ticket_ids: list[str], edge_type: str) -> list[Any]:
        """Return all directed Ticket->Ticket edges of a given type touching any provided ticket id."""
        if not ticket_ids:
            return []
        return self.db.execute(
            GET_TICKET_EDGES_BY_TYPE,
            self._p(ticket_ids=ticket_ids, edge_type=edge_type.strip().upper()),
        )

    # ── Dependencies ──────────────────────────────────────────────────────────

    def add_dependency(self, ticket_id: str, depends_on_id: str) -> None:
        self.db.execute_write(CREATE_DEPEND_ON, self._p(ticket_id=ticket_id, depends_on_id=depends_on_id))

    def remove_dependency(self, ticket_id: str, depends_on_id: str) -> None:
        self.db.execute_write(DELETE_DEPEND_ON, self._p(ticket_id=ticket_id, depends_on_id=depends_on_id))

    def get_dependencies(self, ticket_id: str) -> list[Any]:
        """Return Ticket nodes this ticket depends on, within this workspace."""
        return self.db.execute(GET_DEPENDENCIES, self._p(ticket_id=ticket_id))

    def get_dependents(self, ticket_id: str) -> list[Any]:
        """Return Ticket nodes that depend on this ticket, within this workspace."""
        return self.db.execute(GET_DEPENDENTS, self._p(ticket_id=ticket_id))

    # ── Relations ─────────────────────────────────────────────────────────────

    def add_relation(self, ticket_id: str, related_id: str) -> None:
        self.db.execute_write(CREATE_RELATES_TO, self._p(ticket_id=ticket_id, related_id=related_id))

    def remove_relation(self, ticket_id: str, related_id: str) -> None:
        self.db.execute_write(DELETE_RELATES_TO, self._p(ticket_id=ticket_id, related_id=related_id))

    def get_related(self, ticket_id: str) -> list[Any]:
        """Return Ticket nodes related to this ticket (undirected), within this workspace."""
        return self.db.execute(GET_RELATED, self._p(ticket_id=ticket_id))

    # ── User associations ─────────────────────────────────────────────────────

    def assign_user(self, user_id: str, ticket_id: str) -> None:
        self.db.execute_write(CREATE_ASSIGNED, self._p(user_id=user_id, ticket_id=ticket_id))

    def unassign_user(self, user_id: str, ticket_id: str) -> None:
        self.db.execute_write(DELETE_ASSIGNED, self._p(user_id=user_id, ticket_id=ticket_id))

    def get_assigned_users(self, ticket_id: str) -> list[Any]:
        """Return User nodes assigned to this ticket."""
        return self.db.execute(GET_ASSIGNED_USERS, self._p(ticket_id=ticket_id))

    def set_creator(self, user_id: str, ticket_id: str) -> None:
        self.db.execute_write(CREATE_CREATED, self._p(user_id=user_id, ticket_id=ticket_id))

    def get_creator(self, ticket_id: str) -> list[Any]:
        """Return the User node that created this ticket."""
        return self.db.execute(GET_CREATOR, self._p(ticket_id=ticket_id))

    # ── Scheduling ────────────────────────────────────────────────────────────

    def schedule(self, ticket_id: str, timebox_id: str) -> None:
        self.db.execute_write(CREATE_SCHEDULED, self._p(ticket_id=ticket_id, timebox_id=timebox_id))

    def get_scheduled_timebox(self, ticket_id: str) -> list[Any]:
        """Return the Timebox node this ticket is scheduled in, within this workspace."""

        return self.db.execute(GET_SCHEDULED_TIMEBOX, self._p(ticket_id=ticket_id))

    # ── Goal ──────────────────────────────────────────────────────────────

    def add_goal(self, ticket_id: str, goal_id: str) -> None:
        """Ticket EXECUTES Goal."""
        self.db.execute_write(CREATE_EXECUTES, self._p(ticket_id=ticket_id, goal_id=goal_id))

    def remove_goal(self, ticket_id: str, goal_id: str) -> None:
        """Remove Ticket EXECUTES Goal."""
        self.db.execute_write(DELETE_EXECUTES, self._p(ticket_id=ticket_id, goal_id=goal_id))

    def get_goals(self, ticket_id: str) -> list[Any]:
        """Get goals executed by this ticket."""

        return self.db.execute(GET_TICKET_GOALS, self._p(ticket_id=ticket_id))
