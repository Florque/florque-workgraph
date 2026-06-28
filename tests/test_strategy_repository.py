import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.strategy_repository import StrategyRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def strategy_repo(mock_db):
    return StrategyRepository(mock_db, "test_workspace")

def test_create(strategy_repo):
    strategy_data = {"id": "strat1", "title": "Test Strategy"}
    strategy_repo.create(strategy_data)
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_STRATEGY,
        {'workspace_id': 'test_workspace', 'id': 'strat1', 'title': 'Test Strategy', 'archived': None, 'is_project': None}
    )

def test_update(strategy_repo):
    updates = {"title": "New Title"}
    strategy_repo.update("strat1", updates)
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.UPDATE_STRATEGY,
        {'workspace_id': 'test_workspace', 'id': 'strat1', 'title': 'New Title', 'description': None, 'is_project': None, 'archived': None}
    )

def test_get(strategy_repo):
    strategy_repo.get("strat1")
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_STRATEGY,
        {'workspace_id': 'test_workspace', 'id': 'strat1'}
    )

def test_get_all(strategy_repo):
    strategy_repo.get_all()
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_PROJECTS_FOR_WORKSPACE,
        {'workspace_id': 'test_workspace', 'include_archived': False}
    )

def test_delete(strategy_repo):
    strategy_repo.get_goals = MagicMock(return_value=[])
    strategy_repo.delete("strat1")
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_STRATEGY,
        {'workspace_id': 'test_workspace', 'id': 'strat1'}
    )

def test_delete_with_goals_raises_error(strategy_repo):
    strategy_repo.get_goals = MagicMock(return_value=["goal1"])
    with pytest.raises(ValueError):
        strategy_repo.delete("strat1")

def test_add_goal(strategy_repo):
    strategy_repo.add_goal("strat1", "goal1")
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_TRACKS_VIA,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'goal_id': 'goal1'}
    )

def test_remove_goal(strategy_repo):
    strategy_repo.remove_goal("strat1", "goal1")
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_TRACKS_VIA,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'goal_id': 'goal1'}
    )

def test_get_goals(strategy_repo):
    strategy_repo.get_goals("strat1")
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_STRATEGY_GOALS,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'include_archived': False}
    )

def test_create_ticket(strategy_repo):
    ticket_data = {"id": "ticket1", "title": "Test Ticket", "type": "creative"}
    strategy_repo.create_ticket("strat1", ticket_data)
    strategy_repo.db.execute_write.assert_any_call(
        queries.CREATE_TICKET,
        {'workspace_id': 'test_workspace', **ticket_data, 'archived': None}
    )
    strategy_repo.db.execute_write.assert_any_call(
        queries.ADD_TICKET_TO_STRATEGY,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'ticket_id': 'ticket1'}
    )

def test_remove_ticket(strategy_repo):
    strategy_repo.remove_ticket("strat1", "ticket1")
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.REMOVE_TICKET_FROM_STRATEGY,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'ticket_id': 'ticket1'}
    )

def test_get_tickets(strategy_repo):
    strategy_repo.get_tickets("strat1")
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_TICKETS_FOR_STRATEGY,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1'}
    )

def test_set_archived_status(strategy_repo):
    strategy_repo.set_archived_status("strat1", True)
    strategy_repo.db.execute_write.assert_called_once_with(
        queries.SET_STRATEGY_ARCHIVED_STATUS,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1', 'archived': True}
    )

def test_get_strategy_workgraph(strategy_repo):
    strategy_repo.get_strategy_workgraph("strat1")
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_STRATEGY_WORKGRAPH,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1'}
    )

def test_get_requiring_tickets(strategy_repo):
    strategy_repo.get_requiring_tickets("strat1")
    strategy_repo.db.execute.assert_called_once_with(
        queries.GET_TICKETS_REQUIRING_STRATEGY,
        {'workspace_id': 'test_workspace', 'strategy_id': 'strat1'}
    )
