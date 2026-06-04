import pytest
from florque_workgraph.repositories import (
    CapabilityRepository,
    ProjectRepository,
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
        "project": lambda workspace_id: ProjectRepository(florque_workgraph, workspace_id),
        "user": UserRepository(florque_workgraph),
        "role": lambda workspace_id: RoleRepository(florque_workgraph, workspace_id),
        "capability": CapabilityRepository(florque_workgraph),
    }

def _create_user(user_repo, user_id, name=None):
    user_repo.create({"id": user_id, "name": name or user_id, "email": f"{user_id}@example.com"})

def _create_workspace(workspace_repo, user_repo, workspace_id="ws-1", creator_id="u-creator"):
    _create_user(user_repo, creator_id)
    workspace_repo.create({"id": workspace_id, "name": workspace_id, "creator_user_id": creator_id})

def _create_project(project_repo, project_id="p-1"):
    project_repo.create({"id": project_id, "name": project_id, "description": f"{project_id} desc"})

def test_role_repository_methods(repos):
    capability_repo = repos["capability"]
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    capability_repo.create({"id": "cap-role-1", "name": "view", "description": "view"})
    capability_repo.create({"id": "cap-role-2", "name": "edit", "description": "edit"})

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-role", creator_id="u-role-owner")
    _create_user(user_repo, "u-role-member")

    project_repo = repos["project"]("ws-role")
    _create_project(project_repo, "p-role")

    role_repo = repos["role"]("ws-role")
    role_repo.create({"id": "r-ws", "name": "WorkspaceRole", "scope": "workspace"})
    role_repo.create({"id": "r-pr", "name": "ProjectRole", "scope": "project", "project_id": "p-role"})

    assert _ids(role_repo.get("r-ws")) == ["r-ws"]
    assert "r-ws" in _ids(role_repo.get_all())
    assert "r-pr" in _ids(role_repo.get_all())
    assert "r-ws" in _ids(role_repo.get_workspace_roles())
    assert _ids(role_repo.get_project_roles("p-role")) == ["r-pr"]

    role_repo.add_capability("r-ws", "cap-role-1")
    assert _ids(role_repo.get_capabilities("r-ws")) == ["cap-role-1"]
    assert "r-ws" in _ids(role_repo.get_roles_with_capability("cap-role-1"))

    user_repo.assign_role("u-role-member", "r-ws", "ws-role")
    assert "u-role-member" in _ids(role_repo.get_users("r-ws"))

    role_repo.remove_capability("r-ws", "cap-role-1")
    assert role_repo.get_capabilities("r-ws") == []

    role_repo.delete("r-pr")
    assert role_repo.get("r-pr") == []
