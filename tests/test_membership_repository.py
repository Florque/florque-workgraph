import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.membership_repository import MembershipRepository
from florque_workgraph.queries import queries
from florque_workgraph.queries import authorization

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def membership_repo(mock_db):
    return MembershipRepository(mock_db)

def test_create(membership_repo):
    membership_repo.db.execute.return_value = [1] # Mock workspace existence
    membership_repo.create("user1", "ws1", email="user1@example.com", membership_id="member1")

    membership_repo.db.execute.assert_called_once_with(
        queries.GET_WORKSPACE,
        {"id": "ws1"}
    )
    
    membership_repo.db.execute_write.assert_any_call(
        authorization.CREATE_MEMBERSHIP,
        {"id": "member1", "user_id": "user1", "workspace_id": "ws1", "email": "user1@example.com"}
    )
    membership_repo.db.execute_write.assert_any_call(
        authorization.CREATE_HAS_MEMBERSHIP,
        {"user_id": "user1", "membership_id": "member1", "workspace_id": "ws1"}
    )
    membership_repo.db.execute_write.assert_any_call(
        authorization.CREATE_MEMBERSHIP_IN_WORKSPACE,
        {"membership_id": "member1", "workspace_id": "ws1"}
    )

def test_get(membership_repo):
    membership_repo.get("member1", "ws1")
    membership_repo.db.execute.assert_called_once_with(
        authorization.GET_MEMBERSHIP,
        {"id": "member1", "workspace_id": "ws1"}
    )

def test_get_by_user_workspace(membership_repo):
    membership_repo.get_by_user_workspace("user1", "ws1")
    membership_repo.db.execute.assert_called_once_with(
        authorization.GET_MEMBERSHIP_BY_USER_WORKSPACE,
        {"user_id": "user1", "workspace_id": "ws1"}
    )

def test_delete(membership_repo):
    membership_repo.delete("member1", "ws1")
    membership_repo.db.execute_write.assert_called_once_with(
        authorization.DELETE_MEMBERSHIP,
        {"id": "member1", "workspace_id": "ws1"}
    )

def test_add_role(membership_repo):
    membership_repo.add_role("member1", "role1", "ws1")
    membership_repo.db.execute_write.assert_called_once_with(
        authorization.CREATE_MEMBERSHIP_HAS_ROLE,
        {"membership_id": "member1", "role_id": "role1", "workspace_id": "ws1"}
    )

def test_remove_role(membership_repo):
    membership_repo.remove_role("member1", "role1", "ws1")
    membership_repo.db.execute_write.assert_called_once_with(
        authorization.DELETE_MEMBERSHIP_HAS_ROLE,
        {"membership_id": "member1", "role_id": "role1", "workspace_id": "ws1"}
    )

def test_get_roles(membership_repo):
    membership_repo.get_roles("member1", "ws1")
    membership_repo.db.execute.assert_called_once_with(
        authorization.GET_MEMBERSHIP_ROLES,
        {"membership_id": "member1", "workspace_id": "ws1"}
    )
