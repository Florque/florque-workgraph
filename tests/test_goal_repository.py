import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.goal_repository import GoalRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def goal_repo(mock_db):
    return GoalRepository(mock_db, "test_workspace")

def test_create(goal_repo):
    goal_data = {"id": "goal1", "title": "Test Goal"}
    goal_repo.create(goal_data, "strat1")
    goal_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_GOAL_TRACKING_STRATEGY,
        {'id': 'goal1', 'title': 'Test Goal', 'archived': False, 'strategy_id': 'strat1', 'workspace_id': 'test_workspace'}
    )

def test_update(goal_repo):
    updates = {"title": "New Title"}
    goal_repo.update("goal1", updates)
    goal_repo.db.execute_write.assert_called_once_with(
        queries.UPDATE_GOAL,
        {'id': 'goal1', 'workspace_id': 'test_workspace', 'title': 'New Title', 'description': None, 'archived': None}
    )

def test_get(goal_repo):
    goal_repo.get("goal1")
    goal_repo.db.execute.assert_called_once_with(
        queries.GET_GOAL,
        {'workspace_id': 'test_workspace', 'id': 'goal1'}
    )

def test_get_all(goal_repo):
    goal_repo.get_all()
    goal_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_GOALS,
        {'workspace_id': 'test_workspace', 'include_archived': False}
    )

def test_delete(goal_repo):
    goal_repo.get_tickets = MagicMock(return_value=[])
    goal_repo.delete("goal1")
    goal_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_GOAL,
        {'workspace_id': 'test_workspace', 'id': 'goal1'}
    )

def test_delete_with_tickets_raises_error(goal_repo):
    goal_repo.get_tickets = MagicMock(return_value=["ticket1"])
    with pytest.raises(ValueError):
        goal_repo.delete("goal1")

def test_get_strategy(goal_repo):
    goal_repo.get_strategy("goal1")
    goal_repo.db.execute.assert_called_once_with(
        queries.GET_GOAL_STRATEGY,
        {'workspace_id': 'test_workspace', 'goal_id': 'goal1'}
    )

def test_get_tickets(goal_repo):
    goal_repo.get_tickets("goal1")
    goal_repo.db.execute.assert_called_once_with(
        queries.GET_GOAL_TICKETS,
        {'workspace_id': 'test_workspace', 'goal_id': 'goal1'}
    )

def test_set_archived_status(goal_repo):
    goal_repo.set_archived_status("goal1", True)
    goal_repo.db.execute_write.assert_called_once_with(
        queries.SET_GOAL_ARCHIVED_STATUS,
        {'workspace_id': 'test_workspace', 'goal_id': 'goal1', 'archived': True}
    )
