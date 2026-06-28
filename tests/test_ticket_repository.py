import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.ticket_repository import TicketRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def ticket_repo(mock_db):
    return TicketRepository(mock_db, "test_workspace")

def test_create(ticket_repo):
    ticket_data = {"id": "ticket1", "type": "creative"}
    ticket_repo.create(ticket_data)
    ticket_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_TICKET,
        {'workspace_id': 'test_workspace', 'id': 'ticket1', 'type': 'creative', 'archived': None}
    )

def test_create_with_parent(ticket_repo):
    ticket_data = {"id": "child1", "parent_id": "parent1", "type": "reactive"}
    ticket_repo.create(ticket_data)
    ticket_repo.db.execute_write.assert_any_call(
        queries.CREATE_TICKET,
        {'workspace_id': 'test_workspace', **ticket_data, 'archived': None}
    )
    ticket_repo.db.execute_write.assert_any_call(
        queries.CREATE_SUBTASK,
        {'workspace_id': 'test_workspace', 'parent_id': 'parent1', 'child_id': 'child1', 'archived': None}
    )

def test_create_with_goal(ticket_repo):
    ticket_data = {"id": "ticket1", "goal_id": "goal1", "type": "creative"}
    ticket_repo.create(ticket_data)
    ticket_repo.db.execute_write.assert_any_call(
        queries.CREATE_TICKET,
        {'workspace_id': 'test_workspace', **ticket_data, 'archived': None}
    )
    ticket_repo.db.execute_write.assert_any_call(
        queries.CREATE_EXECUTES,
        {'workspace_id': 'test_workspace', 'ticket_id': 'ticket1', 'goal_id': 'goal1', 'archived': None}
    )

def test_create_invalid_type(ticket_repo):
    with pytest.raises(ValueError):
        ticket_repo.create({"type": "invalid_type"})

def test_get(ticket_repo):
    ticket_repo.get("ticket1")
    ticket_repo.db.execute.assert_called_once_with(
        queries.GET_TICKET,
        {'workspace_id': 'test_workspace', 'id': 'ticket1'}
    )

def test_get_all(ticket_repo):
    ticket_repo.get_all()
    ticket_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_TICKETS,
        {'workspace_id': 'test_workspace'}
    )

def test_add_subtask(ticket_repo):
    ticket_repo.add_subtask("parent_id", "child_id")
    ticket_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_SUBTASK,
        {'workspace_id': 'test_workspace', 'parent_id': 'parent_id', 'child_id': 'child_id', 'archived': None}
    )

def test_remove_subtask(ticket_repo):
    ticket_repo.remove_subtask("parent_id", "child_id")
    ticket_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_SUBTASK,
        {'workspace_id': 'test_workspace', 'parent_id': 'parent_id', 'child_id': 'child_id'}
    )

def test_get_subtasks(ticket_repo):
    ticket_repo.get_subtasks("parent_id")
    ticket_repo.db.execute.assert_called_once_with(
        queries.GET_SUBTASKS,
        {'workspace_id': 'test_workspace', 'parent_id': 'parent_id'}
    )

def test_get_parent_tickets(ticket_repo):
    mock_ticket = MagicMock()
    ticket_repo.db.execute.return_value = [[mock_ticket, True]]
    result = ticket_repo.get_parent_tickets("child_id")
    ticket_repo.db.execute.assert_called_once_with(
        queries.GET_PARENT_TICKETS,
        {'workspace_id': 'test_workspace', 'child_id': 'child_id'}
    )
    assert mock_ticket.is_initiative is True
    assert result == [[mock_ticket, True]]

def test_get_all_subtickets(ticket_repo):
    ticket_repo.get_all_subtickets("ticket_id")
    ticket_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_SUBTICKETS_FOR_TICKET,
        {'workspace_id': 'test_workspace', 'ticket_id': 'ticket_id'}
    )

def test_create_subtask(ticket_repo):
    ticket_repo.get = MagicMock(return_value=[[{"type": "reactive"}]])
    ticket_repo.create = MagicMock()
    ticket_repo.create_subtask("parent_id", {"id": "child_id"})
    ticket_repo.create.assert_called_once_with({'id': 'child_id', 'parent_id': 'parent_id'})

def test_create_subtask_invalid_parent_type(ticket_repo):
    ticket_repo.get = MagicMock(return_value=[[{"type": "creative"}]])
    with pytest.raises(ValueError, match="Subtasks can only be created for tickets of type 'reactive' or 'scheduled'."):
        ticket_repo.create_subtask("parent_id", {"id": "child_id"})

def test_set_archived_status_cascaded(ticket_repo):
    ticket_repo.set_archived_status("ticket_id", True, include_subtickets=True)
    assert ticket_repo.db.execute_write.call_count == 2
    ticket_repo.db.execute_write.assert_any_call(
        queries.SET_TICKET_ARCHIVED_STATUS,
        {'workspace_id': 'test_workspace', 'ticket_id': 'ticket_id', 'archived': True}
    )
    ticket_repo.db.execute_write.assert_any_call(
        queries.SET_SUBTICKETS_ARCHIVED_STATUS_CASCADED,
        {'workspace_id': 'test_workspace', 'ticket_id': 'ticket_id', 'archived': True}
    )
