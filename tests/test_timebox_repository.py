import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.timebox_repository import TimeboxRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def timebox_repo(mock_db):
    return TimeboxRepository(mock_db, "test_workspace")

def test_create(timebox_repo):
    timebox_data = {"id": "tb1", "name": "Test Timebox", "start_date": "2024-01-01", "end_date": "2024-01-07", "status": "active"}
    timebox_repo.create(timebox_data)
    timebox_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_TIMEBOX,
        {'workspace_id': 'test_workspace', **timebox_data}
    )

def test_get(timebox_repo):
    timebox_repo.get("tb1")
    timebox_repo.db.execute.assert_called_once_with(
        queries.GET_TIMEBOX,
        {'workspace_id': 'test_workspace', 'id': 'tb1'}
    )

def test_get_all(timebox_repo):
    timebox_repo.get_all()
    timebox_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_TIMEBOXES,
        {'workspace_id': 'test_workspace'}
    )

def test_delete(timebox_repo):
    timebox_repo.delete("tb1")
    timebox_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_TIMEBOX,
        {'workspace_id': 'test_workspace', 'id': 'tb1'}
    )

def test_schedule_ticket(timebox_repo):
    timebox_repo.schedule_ticket("ticket1", "tb1")
    timebox_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_SCHEDULED,
        {'workspace_id': 'test_workspace', 'ticket_id': 'ticket1', 'timebox_id': 'tb1'}
    )

def test_get_scheduled_tickets(timebox_repo):
    timebox_repo.get_scheduled_tickets("tb1")
    timebox_repo.db.execute.assert_called_once_with(
        queries.GET_SCHEDULED_TICKETS,
        {'workspace_id': 'test_workspace', 'timebox_id': 'tb1'}
    )

def test_get_tickets(timebox_repo):
    timebox_repo.get_tickets("tb1")
    timebox_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_TICKETS_FOR_TIMEBOX,
        {'workspace_id': 'test_workspace', 'timebox_id': 'tb1'}
    )
