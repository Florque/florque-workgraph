import pytest
from unittest.mock import MagicMock, patch, ANY
from florque_workgraph.repositories.workspace_repository import WorkspaceRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def workspace_repo(mock_db):
    return WorkspaceRepository(mock_db)

@patch('florque_workgraph.repositories.workspace_repository.UserRepository')
@patch('florque_workgraph.repositories.workspace_repository.MembershipRepository')
@patch('florque_workgraph.repositories.workspace_repository.CapabilityRepository')
@patch('florque_workgraph.repositories.workspace_repository.get_user_by_id')
def test_create(mock_get_user, MockCapabilityRepo, MockMembershipRepo, MockUserRepo, workspace_repo):
    # Mock node objects with a 'properties' attribute
    mock_membership_node = MagicMock()
    mock_membership_node.properties = {'id': 'member1'}
    mock_capability_node = MagicMock()
    mock_capability_node.properties = {'id': 'cap1'}

    # Setup mock return values
    mock_user_repo = MockUserRepo.return_value
    mock_user_repo.get.return_value = [] # User does not exist
    mock_membership_repo = MockMembershipRepo.return_value
    mock_membership_repo.create.return_value = [[mock_membership_node]]
    mock_capability_repo = MockCapabilityRepo.return_value
    mock_capability_repo.get_all.return_value = [[mock_capability_node]]
    mock_get_user.return_value = None

    workspace_data = {"id": "ws1", "name": "Test Workspace", "creator_user_id": "user1"}
    workspace_repo.create(workspace_data)

    # Assertions
    workspace_repo.db.execute_write.assert_any_call(queries.CREATE_WORKSPACE, {"id": "ws1", "name": "Test Workspace"})
    mock_user_repo.create.assert_called_once()
    mock_membership_repo.create.assert_called_once_with("user1", "ws1")
    workspace_repo.db.execute_write.assert_any_call(queries.CREATE_ROLE, ANY)
    mock_membership_repo.add_role.assert_called_once_with("member1", ANY, "ws1")
    workspace_repo.db.execute_write.assert_any_call(queries.ADD_CAPABILITY_TO_ROLE, ANY)

def test_get(workspace_repo):
    workspace_repo.get("ws1")
    workspace_repo.db.execute.assert_called_once_with(queries.GET_WORKSPACE, {"id": "ws1"})

def test_get_user_workspaces(workspace_repo):
    workspace_repo.get_user_workspaces("user1")
    workspace_repo.db.execute.assert_called_once_with(queries.GET_USER_WORKSPACES, {"user_id": "user1"})

def test_get_user_workspaces_with_email(workspace_repo):
    workspace_repo.get_user_workspaces("user1", email="test@example.com")
    workspace_repo.db.execute_write.assert_called_once_with(queries.LINK_DETACHED_MEMBERSHIPS, {"user_id": "user1", "email": "test@example.com"})
    workspace_repo.db.execute.assert_called_once_with(queries.GET_USER_WORKSPACES, {"user_id": "user1"})

def test_delete(workspace_repo):
    workspace_repo.delete("ws1")
    workspace_repo.db.execute_write.assert_called_once_with(queries.DELETE_WORKSPACE, {"id": "ws1"})

def test_get_projects(workspace_repo):
    workspace_repo.get_projects("ws1")
    workspace_repo.db.execute.assert_called_once_with(queries.GET_PROJECTS_FOR_WORKSPACE, {"workspace_id": "ws1"})

def test_get_tickets(workspace_repo):
    workspace_repo.get_tickets("ws1")
    workspace_repo.db.execute.assert_called_once_with(queries.GET_TICKETS_FOR_WORKSPACE, {"workspace_id": "ws1"})
