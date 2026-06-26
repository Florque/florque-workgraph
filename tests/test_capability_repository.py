import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.capability_repository import CapabilityRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def capability_repo(mock_db):
    return CapabilityRepository(mock_db)

def test_create(capability_repo):
    capability_data = {"id": "cap1", "name": "ticket:create", "description": "Create tickets"}
    capability_repo.create(capability_data)
    capability_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_CAPABILITY,
        capability_data
    )

def test_get(capability_repo):
    capability_repo.get("cap1")
    capability_repo.db.execute.assert_called_once_with(
        queries.GET_CAPABILITY,
        {"id": "cap1"}
    )

def test_get_all(capability_repo):
    capability_repo.get_all()
    capability_repo.db.execute.assert_called_once_with(queries.GET_ALL_CAPABILITIES)

def test_delete(capability_repo):
    capability_repo.delete("cap1")
    capability_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_CAPABILITY,
        {"id": "cap1"}
    )

def test_get_roles_in_workspace(capability_repo):
    capability_repo.get_roles_in_workspace("cap1", "ws1")
    capability_repo.db.execute.assert_called_once_with(
        queries.GET_CAPABILITY_ROLES,
        {"capability_id": "cap1", "workspace_id": "ws1"}
    )
