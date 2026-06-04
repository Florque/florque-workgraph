import pytest
from florque_workgraph.repositories import (
    MembershipRepository,
    RoleRepository,
    UserRepository,
    WorkspaceRepository,
)
from florque_workgraph.session import GraphManager

def _ids(rows):
    return [row[0].properties["id"] for row in rows]

@pytest.fixture(scope="session")
def florque_workgraph():
    host = "localhost"
    port = 7666
    try:
        db = GraphManager(host=host, port=port)
    except Exception as exc:
        pytest.skip(f"Memgraph is not reachable at {host}:{port}: {exc}")
    db.apply_constraints()
    yield db
    db.close()

@pytest.fixture(autouse=True)
def clean_graph(florque_workgraph):
    florque_workgraph.execute_write("MATCH (n) DETACH DELETE n")

@pytest.fixture
def repos(florque_workgraph):
    return {
        "workspace": WorkspaceRepository(florque_workgraph),
        "user": UserRepository(florque_workgraph),
        "role": lambda workspace_id: RoleRepository(florque_workgraph, workspace_id),
        "membership": MembershipRepository(florque_workgraph),
    }

def _create_user(user_repo, user_id, name=None):
    user_repo.create({"id": user_id, "name": name or user_id, "email": f"{user_id}@example.com"})

def _create_workspace(workspace_repo, user_repo, workspace_id="ws-1", creator_id="u-creator"):
    _create_user(user_repo, creator_id)
    workspace_repo.create({"id": workspace_id, "name": workspace_id, "creator_user_id": creator_id})

def test_membership_repository_methods(repos):
    membership_repo = repos["membership"]
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-members", creator_id="u-owner")
    _create_user(user_repo, "u-member")

    role_repo = repos["role"]("ws-members")
    role_repo.create({"id": "role-members", "name": "Member", "scope": "workspace"})

    membership_repo.create("u-member", "ws-members", membership_id="m-1")
    assert _ids(membership_repo.get("m-1")) == ["m-1"]
    assert _ids(membership_repo.get_by_user_workspace("u-member", "ws-members")) == ["m-1"]

    membership_repo.add_role("m-1", "role-members", "ws-members")
    assert _ids(membership_repo.get_roles("m-1", "ws-members")) == ["role-members"]

    membership_repo.remove_role("m-1", "role-members", "ws-members")
    assert membership_repo.get_roles("m-1", "ws-members") == []

    membership_repo.delete("m-1")
    assert membership_repo.get("m-1") == []
