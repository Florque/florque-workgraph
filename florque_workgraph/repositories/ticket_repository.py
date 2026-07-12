from typing import Any
from .strategy_repository import StrategyRepository
from ..session import GraphManager
from ..queries.queries import (
    CREATE_SCHEDULED,
    GET_SCHEDULED_TIMEBOX,
)
from ..queries.ticket import (
    CREATE_TICKET,
    DELETE_TICKET,
    GET_TICKET,
    GET_ALL_TICKETS,
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
    GET_ALL_SUBTICKETS_FOR_TICKET,
    GET_TICKET_EDGES_BY_TYPE,
    UPDATE_TICKET,
    CREATE_EXECUTES,
    DELETE_EXECUTES,
    GET_TICKET_GOALS,
    GET_ANCESTORS_WITH_GOALS,
    SET_TICKET_ARCHIVED_STATUS,
    SET_SUBTICKETS_ARCHIVED_STATUS_CASCADED,
    CREATE_REQUIRES_STRATEGY,
    GET_TICKET_STRATEGY,
    GET_INITIATING_STRATEGY,
    GET_REASONING_CONTEXT,
    GET_PROJECTS_FOR_WORKSPACE,
    GET_TICKET_WORKGRAPH,
    SEARCH_TICKETS,
)
from ..queries.strategy import CREATE_STRATEGY
from ..queries.user import (
    CREATE_ASSIGNED,
    DELETE_ASSIGNED,
    GET_ASSIGNED_USERS,
    CREATE_CREATED,
    GET_CREATOR,
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
    
    def create_root_ticket(self, ticket_data: dict) -> list[Any]:
        """Create a root Ticket node (not a subtask)."""
        params = self._p(**ticket_data)
        params.setdefault("archived", None)
        params.setdefault("is_project", None)
        
        ticket_id = ticket_data.get("id")
        
        rows = self.db.execute_write(CREATE_TICKET, params)

        if not rows:
            raise ValueError(f"Ticket with id {ticket_id} could not be created. It may already exist or there may be a conflict.")

        return rows

    # Create a ticket linking to a parent ticket and optionally linking to a goal. If parent_ticket_id is provided, the ticket will be created as a subtask of that parent ticket.
    # If goal_id is provided, the ticket will be created as executing that goal.
    def create(self, ticket_data: dict, parent_ticket_id: str = None) -> list[Any]:
        """Create a Ticket node."""
        print(f"Creating ticket with data: {ticket_data} and parent_ticket_id: {parent_ticket_id}")
        if not parent_ticket_id:
            parent_ticket_id = ticket_data.get("parent_id")
        # goal_id = ticket_data.get("goal_id")

        params = self._p(**ticket_data)
        params.setdefault("archived", None)
        params.setdefault("is_project", None)
        
        ticket_id = ticket_data.get("id")
        
        rows = self.db.execute_write(CREATE_TICKET, params)
        # handle possible id duplication or other issues by checking if the ticket was actually created
        if not rows:
            raise ValueError(f"Ticket with id {ticket_id} could not be created. It may already exist or there may be a conflict.")
        
        print(f"Ticket created with id {ticket_id}.")

        if ticket_id:
            if parent_ticket_id:
                self.db.execute_write(CREATE_SUBTASK, self._p(parent_id=parent_ticket_id, child_id=ticket_id, archived=None))
                print(f"Subtask relationship created between parent ticket {parent_ticket_id} and child ticket {ticket_id}.")
            # elif goal_id:
            #     self.db.execute_write(CREATE_EXECUTES, self._p(ticket_id=ticket_id, goal_id=goal_id, archived=None))
        return rows

    def update(self, ticket_id: str, updates: dict) -> list[Any]:
        """Update fields on a Ticket node. `updates` may include title, description, status.

        Memgraph requires referenced parameters to be present even when NULL, so ensure
        all expected params exist (set to None when not provided).
        """
        if "type" in updates and updates["type"] and updates["type"] not in ["creative", "reactive", "scheduled"]:
            raise ValueError("Ticket type must be one of 'creative', 'reactive', or 'scheduled'.")

        params = {
            "id": ticket_id,
            "workspace_id": self.workspace_id,
            "title": updates.get("title", None),
            "description": updates.get("description", None),
            "status": updates.get("status", None),
            # "type": updates.get("type", None),
            "is_project": updates.get("is_project", None),
            "archived": updates.get("archived", None),
        }
        self.db.execute_write(UPDATE_TICKET, params)
        
        tickets = self.get(ticket_id)
        
        if len(tickets) == 0:
            raise ValueError(f"Ticket with id {ticket_id} could not be updated. It may not exist.")
        
        if len(tickets) > 1:
            raise ValueError(f"Multiple tickets with id {ticket_id} found. This should not happen in a properly scoped workspace.")
        
        ticket = tickets[0]
        if ticket:
            ticket_node = ticket[0]
            is_initiative = ticket[2] if len(ticket) > 2 else False
            if hasattr(ticket_node, "properties") and isinstance(ticket_node.properties, dict):
                ticket_node.properties['is_initiative'] = is_initiative
            elif isinstance(ticket_node, dict):
                ticket_node['is_initiative'] = is_initiative
        else:
            raise ValueError(f"Ticket with id {ticket_id} could not be updated. It may not exist.")
        # for ticket in tickets:
        #     ticket_node = ticket[0]
        #     is_initiative = ticket[2] if len(ticket) > 2 else False
        #     if hasattr(ticket_node, "properties") and isinstance(ticket_node.properties, dict):
        #         ticket_node.properties['is_initiative'] = is_initiative
        #     elif isinstance(ticket_node, dict):
        #         ticket_node['is_initiative'] = is_initiative
                
        #TODO: switch to single ticket return since we are updating by id and should only have one result
        return tickets


    def set_archived_status(self, ticket_id: str, archived: bool, include_subtickets: bool = False) -> list[Any]:
        """Set the archived status of a ticket and its incoming relationship, optionally cascading to subtickets."""
        params = self._p(ticket_id=ticket_id, archived=archived)
        
        # Always archive the primary ticket first
        result = self.db.execute_write(SET_TICKET_ARCHIVED_STATUS, params)
        
        # If cascading is requested, run the second query
        if include_subtickets:
            self.db.execute_write(SET_SUBTICKETS_ARCHIVED_STATUS_CASCADED, params)
            
        return result

    def get(self, ticket_id: str) -> list[Any]:
        """Return a single Ticket node by id, scoped to this workspace."""
        return self.db.execute(GET_TICKET, self._p(id=ticket_id))

    def get_all(self) -> list[Any]:
        """Return all Ticket nodes in this workspace."""
        return self.db.execute(GET_ALL_TICKETS, self._p())

    def search(self, search_string: str) -> list[Any]:
        """Return all Ticket nodes in this workspace that match the search string."""
        return self.db.execute(SEARCH_TICKETS, self._p(search_string=search_string))

    def get_projects(self) -> list[Any]:
        """Return all Ticket nodes in this workspace that are projects (is_project: true)."""
        return self.db.execute(GET_PROJECTS_FOR_WORKSPACE, self._p())

    def delete(self, ticket_id: str) -> None:
        """Detach-delete a Ticket node within this workspace."""
        self.db.execute_write(DELETE_TICKET, self._p(id=ticket_id))

    # ── Hierarchy ──────────────────────────────────────────────────────────────
    
    #TODO: duplication with create
    # def create_subtask(self, parent_ticket_id: str, subtask_data: dict) -> list[Any]:
    #     """Create a subtask for a ticket, with guards based on ticket type."""
    #     parent_ticket_result = self.get(parent_ticket_id)
    #     if not parent_ticket_result:
    #         raise ValueError(f"Parent ticket with id {parent_ticket_id} not found.")
        
    #     # parent_node = parent_ticket_result[0][0]
    #     # parent_type = parent_node.properties.get("type") if hasattr(parent_node, "properties") else parent_node.get("type")
        
    #     # if parent_type not in ["reactive", "scheduled"]:
    #     #     raise ValueError("Subtasks can only be created for tickets of type 'reactive' or 'scheduled'.")
        
    #     subtask_data["parent_id"] = parent_ticket_id
    #     return self.create(subtask_data)

    def add_subtask(self, parent_id: str, child_id: str) -> None:
        self.db.execute_write(CREATE_SUBTASK, self._p(parent_id=parent_id, child_id=child_id, archived=None))

    # remove INITIATES edge
    def remove_subtask(self, parent_id: str, child_id: str) -> None:
        self.db.execute_write(DELETE_SUBTASK, self._p(parent_id=parent_id, child_id=child_id))

    def get_subtasks(self, parent_id: str) -> list[Any]:
        """Return direct child Ticket nodes within this workspace."""
        return self.db.execute(GET_SUBTASKS, self._p(parent_id=parent_id))

    def get_parent_tickets(self, child_id: str) -> list[Any]:
        """Return direct parent Ticket nodes within this workspace."""
        parent_tickets = self.db.execute(GET_PARENT_TICKETS, self._p(child_id=child_id))
        for ticket in parent_tickets:
            ticket_node = ticket[0]
            is_initiative = ticket[1] if len(ticket) > 1 else False
            if hasattr(ticket_node, "properties") and isinstance(ticket_node.properties, dict):
                ticket_node.properties['is_initiative'] = is_initiative
        return parent_tickets

    def get_all_subtickets(self, ticket_id: str) -> list[Any]:
        """Return all descendant Ticket nodes (recursive via SUBTASK) within this workspace."""
        return self.db.execute(GET_ALL_SUBTICKETS_FOR_TICKET, self._p(ticket_id=ticket_id))

    def get_ticket_workgraph(self, ticket_id: str) -> list[Any]:
        """Return a structure representing the subtask/initiates workgraph starting from the given ticket."""
        return self.db.execute(GET_TICKET_WORKGRAPH, self._p(ticket_id=ticket_id))

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
        self.db.execute_write(CREATE_EXECUTES, self._p(ticket_id=ticket_id, goal_id=goal_id, archived=None))

    def remove_goal(self, ticket_id: str, goal_id: str) -> None:
        """Remove Ticket EXECUTES Goal."""
        self.db.execute_write(DELETE_EXECUTES, self._p(ticket_id=ticket_id, goal_id=goal_id))

    def get_goals(self, ticket_id: str) -> list[Any]:
        """Get goals executed by this ticket."""

        return self.db.execute(GET_TICKET_GOALS, self._p(ticket_id=ticket_id))

    def get_ancestors_with_goals(self, ticket_id: str) -> list[Any]:
        """Get ancestors of a ticket with their goals, ordered by distance."""
        return self.db.execute(GET_ANCESTORS_WITH_GOALS, self._p(ticket_id=ticket_id))

    def get_reasoning_context(self, ticket_id: str) -> list[Any]:
        """Get reasoning context of a ticket recursively upwards."""
        return self.db.execute(GET_REASONING_CONTEXT, self._p(ticket_id=ticket_id))
    
    # ── Strategy ──────────────────────────────────────────────────────────────

    def create_strategy(self, ticket_id: str, strategy_data: dict) -> list[Any]:
        """Create a downstream strategy for a ticket, with guards based on ticket type."""
        ticket_result = self.get(ticket_id)
        if not ticket_result:
            raise ValueError(f"Ticket with id {ticket_id} not found.")

        existing_strategy = self.get_ticket_strategy(ticket_id)
        if existing_strategy:
            raise ValueError(f"Ticket with id {ticket_id} already has an associated strategy.")

        strategy_repo = StrategyRepository(self.db, self.workspace_id)
        strategy_id = strategy_data.get("id")
        
        rows = strategy_repo.create(strategy_data)
        
        if strategy_id:
            self.db.execute_write(
                CREATE_REQUIRES_STRATEGY, self._p(ticket_id=ticket_id, strategy_id=strategy_id)
            )
        return rows

    def get_ticket_strategy(self, ticket_id: str) -> list[Any]:
        """Get the strategy that is required by this ticket."""
        return self.db.execute(GET_TICKET_STRATEGY, self._p(ticket_id=ticket_id))

    def get_initiating_strategy(self, ticket_id: str) -> list[Any]:
        """Get the strategy that initiates this ticket."""
        return self.db.execute(GET_INITIATING_STRATEGY, self._p(ticket_id=ticket_id))

    def get_reasoning_context(self, ticket_id: str) -> list[Any]:
        """Traverses up parent tickets and strategies up to the nearest project."""
        return self.db.execute(GET_REASONING_CONTEXT, self._p(ticket_id=ticket_id))
