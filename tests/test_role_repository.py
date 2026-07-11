import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.role_repository import RoleRepository
from florque_workgraph.queries import (
    queries,
    authorization,
)

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def role_repo(mock_db):
    return RoleRepository(mock_db, "test_workspace")

def test_create(role_repo):
    role_data = {"id": "role1", "name": "Test Role", "scope": "workspace"}
    role_repo.create(role_data)
    role_repo.db.execute_write.assert_called_once_with(
        authorization.CREATE_ROLE,
        {'id': 'role1', 'name': 'Test Role', 'scope': 'workspace', 'workspace_id': 'test_workspace'}
    )

def test_get(role_repo):
    role_repo.get("role1")
    role_repo.db.execute.assert_called_once_with(
        queries.GET_ROLE,
        {'workspace_id': 'test_workspace', 'id': 'role1'}
    )

def test_get_all(role_repo):
    role_repo.get_all()
    role_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_ROLES,
        {'workspace_id': 'test_workspace'}
    )

def test_get_workspace_roles(role_repo):
    role_repo.get_workspace_roles()
    role_repo.db.execute.assert_called_once_with(
        queries.GET_WORKSPACE_ROLES,
        {'workspace_id': 'test_workspace'}
    )

def test_delete(role_repo):
    role_repo.delete("role1")
    role_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_ROLE,
        {'workspace_id': 'test_workspace', 'id': 'role1'}
    )

def test_add_capability(role_repo):
    role_repo.add_capability("role1", "cap1")
    role_repo.db.execute_write.assert_called_once_with(
        queries.ADD_CAPABILITY_TO_ROLE,
        {'workspace_id': 'test_workspace', 'role_id': 'role1', 'capability_id': 'cap1'}
    )

def test_remove_capability(role_repo):
    role_repo.remove_capability("role1", "cap1")
    role_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_HAS_CAPABILITY,
        {'workspace_id': 'test_workspace', 'role_id': 'role1', 'capability_id': 'cap1'}
    )

def test_get_capabilities(role_repo):
    role_repo.get_capabilities("role1")
    role_repo.db.execute.assert_called_once_with(
        queries.GET_ROLE_CAPABILITIES,
        {'workspace_id': 'test_workspace', 'role_id': 'role1'}
    )

def test_get_roles_with_capability(role_repo):
    role_repo.get_roles_with_capability("cap1")
    role_repo.db.execute.assert_called_once_with(
        queries.GET_CAPABILITY_ROLES,
        {'workspace_id': 'test_workspace', 'capability_id': 'cap1'}
    )

def test_get_users(role_repo):
    role_repo.get_users("role1")
    role_repo.db.execute.assert_called_once_with(
        queries.GET_ROLE_USERS,
        {'workspace_id': 'test_workspace', 'role_id': 'role1'}
    )
