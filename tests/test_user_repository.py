import pytest
from unittest.mock import MagicMock, patch
from florque_workgraph.repositories.user_repository import UserRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def user_repo(mock_db):
    return UserRepository(mock_db)

def test_create(user_repo):
    user_data = {"id": "user1", "name": "Test User", "email": "test@example.com"}
    user_repo.create(user_data)
    user_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_USER,
        user_data
    )

def test_get(user_repo):
    user_repo.get("user1")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_USER,
        {"id": "user1"}
    )

def test_get_by_email(user_repo):
    user_repo.get_by_email("test@example.com")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_USER_BY_EMAIL,
        {"email": "test@example.com"}
    )

def test_get_workspace_users(user_repo):
    user_repo.get_workspace_users("ws1")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_WORKSPACE_USERS,
        {"workspace_id": "ws1"}
    )

def test_delete(user_repo):
    user_repo.delete("user1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_USER,
        {"id": "user1"}
    )

def test_assign_to_ticket(user_repo):
    user_repo.assign_to_ticket("user1", "ticket1", "ws1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_ASSIGNED,
        {"user_id": "user1", "ticket_id": "ticket1", "workspace_id": "ws1"}
    )

def test_unassign_from_ticket(user_repo):
    user_repo.unassign_from_ticket("user1", "ticket1", "ws1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_ASSIGNED,
        {"user_id": "user1", "ticket_id": "ticket1", "workspace_id": "ws1"}
    )

def test_get_assigned_tickets(user_repo):
    user_repo.get_assigned_tickets("user1", "ws1")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_TICKETS_FOR_ASSIGNEE,
        {"user_id": "user1", "workspace_id": "ws1"}
    )

def test_set_ticket_creator(user_repo):
    user_repo.set_ticket_creator("user1", "ticket1", "ws1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_CREATED,
        {"user_id": "user1", "ticket_id": "ticket1", "workspace_id": "ws1"}
    )

def test_get_created_tickets(user_repo):
    user_repo.get_created_tickets("user1", "ws1")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_CREATED_TICKETS,
        {"user_id": "user1", "workspace_id": "ws1"}
    )

@patch('florque_workgraph.repositories.user_repository.MembershipRepository')
def test_assign_role(MockMembershipRepo, user_repo):
    mock_membership_repo = MockMembershipRepo.return_value
    mock_membership_repo.get_by_user_workspace.return_value = []
    mock_membership_repo.create.return_value = ([{'id': 'member1'}],) # Simplified mock
    user_repo._row_to_dict = MagicMock(return_value={'id': 'member1'})
    user_repo.assign_role("user1", "role1", "ws1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_MEMBERSHIP_HAS_ROLE,
        {"membership_id": "member1", "role_id": "role1", "workspace_id": "ws1"}
    )

@patch('florque_workgraph.repositories.user_repository.MembershipRepository')
def test_revoke_role(MockMembershipRepo, user_repo):
    mock_membership_repo = MockMembershipRepo.return_value
    mock_membership_repo.get_by_user_workspace.return_value = ([{'id': 'member1'}],)
    user_repo._row_to_dict = MagicMock(return_value={'id': 'member1'})
    user_repo.revoke_role("user1", "role1", "ws1")
    user_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_MEMBERSHIP_HAS_ROLE,
        {"membership_id": "member1", "role_id": "role1", "workspace_id": "ws1"}
    )

@patch('florque_workgraph.repositories.user_repository.MembershipRepository')
def test_get_roles(MockMembershipRepo, user_repo):
    mock_membership_repo = MockMembershipRepo.return_value
    mock_membership_repo.get_by_user_workspace.return_value = ([{'id': 'member1'}],)
    user_repo._row_to_dict = MagicMock(return_value={'id': 'member1'})
    user_repo.get_roles("user1", "ws1")
    user_repo.db.execute.assert_called_once_with(
        queries.GET_MEMBERSHIP_ROLES,
        {"membership_id": "member1", "workspace_id": "ws1"}
    )
