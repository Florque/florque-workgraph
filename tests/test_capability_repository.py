import pytest
from florque_workgraph.repositories import (
    CapabilityRepository,
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
        "capability": CapabilityRepository(florque_workgraph),
    }

def _create_user(user_repo, user_id, name=None):
    user_repo.create({"id": user_id, "name": name or user_id, "email": f"{user_id}@example.com"})

def _create_workspace(workspace_repo, user_repo, workspace_id="ws-1", creator_id="u-creator"):
    _create_user(user_repo, creator_id)
    workspace_repo.create({"id": workspace_id, "name": workspace_id, "creator_user_id": creator_id})

def test_capability_repository_methods(repos):
    capability_repo = repos["capability"]
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    capability_repo.create({"id": "cap-1", "name": "ticket:create", "description": "create tickets"})
    capability_repo.create({"id": "cap-2", "name": "ticket:update", "description": "update tickets"})

    assert _ids(capability_repo.get("cap-1")) == ["cap-1"]
    assert set(_ids(capability_repo.get_all())) == {"cap-1", "cap-2"}

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-cap", creator_id="u-cap")
    role_repo = repos["role"]("ws-cap")
    role_repo.create({"id": "role-cap", "name": "CapRole", "scope": "workspace"})
    role_repo.add_capability("role-cap", "cap-1")

    roles = capability_repo.get_roles_in_workspace("cap-1", "ws-cap")
    assert "role-cap" in _ids(roles)

    capability_repo.delete("cap-2")
    assert capability_repo.get("cap-2") == []
