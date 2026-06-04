import pytest
from florque_workgraph.repositories import (
    GoalRepository,
    ProjectRepository,
    RoleRepository,
    StrategyRepository,
    TicketRepository,
    UserRepository,
    VisionRepository,
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
        "ticket": lambda workspace_id: TicketRepository(florque_workgraph, workspace_id),
        "role": lambda workspace_id: RoleRepository(florque_workgraph, workspace_id),
        "user": UserRepository(florque_workgraph),
        "vision": lambda workspace_id: VisionRepository(florque_workgraph, workspace_id),
        "strategy": lambda workspace_id: StrategyRepository(florque_workgraph, workspace_id),
        "goal": lambda workspace_id: GoalRepository(florque_workgraph, workspace_id),
    }

def _create_user(user_repo, user_id, name=None):
    user_repo.create({"id": user_id, "name": name or user_id, "email": f"{user_id}@example.com"})

def _create_workspace(workspace_repo, user_repo, workspace_id="ws-1", creator_id="u-creator"):
    _create_user(user_repo, creator_id)
    workspace_repo.create({"id": workspace_id, "name": workspace_id, "creator_user_id": creator_id})

def _create_project(project_repo, project_id="p-1"):
    project_repo.create({"id": project_id, "name": project_id, "description": f"{project_id} desc"})

def _create_vision(vision_repo, vision_id, project_id):
    vision_repo.create({"id": vision_id, "name": vision_id, "title": vision_id, "description": f"{vision_id} desc", "project_id": project_id})

def _create_strategy(strategy_repo, strategy_id, vision_id):
    strategy_repo.create({"id": strategy_id, "name": strategy_id, "title": strategy_id, "description": f"{strategy_id} desc"}, vision_id)

def _create_goal(goal_repo, goal_id, strategy_id):
    goal_repo.create({"id": goal_id, "name": goal_id, "title": goal_id, "description": f"{goal_id} desc"}, strategy_id)

def _create_ticket(ticket_repo, ticket_id, project_id, parent_id=None, goal_id=None):
    ticket_data = {
        "id": ticket_id,
        "title": f"title {ticket_id}",
        "description": f"desc {ticket_id}",
        "status": "todo",
        "project_id": project_id,
    }
    if parent_id:
        ticket_data["parent_id"] = parent_id
    if goal_id:
        ticket_data["goal_id"] = goal_id
    ticket_repo.create(ticket_data)

def test_user_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]
    _create_user(user_repo, "u-main")
    _create_user(user_repo, "u-other")

    workspace_repo.create({"id": "ws-user", "name": "ws-user", "creator_user_id": "u-main"})

    project_repo = repos["project"]("ws-user")
    ticket_repo = repos["ticket"]("ws-user")
    role_repo = repos["role"]("ws-user")
    vision_repo = repos["vision"]("ws-user")
    strategy_repo = repos["strategy"]("ws-user")
    goal_repo = repos["goal"]("ws-user")

    _create_project(project_repo, "p-user")
    _create_vision(vision_repo, "v-1", "p-user")
    _create_strategy(strategy_repo, "s-1", "v-1")
    _create_goal(goal_repo, "g-1", "s-1")
    _create_ticket(ticket_repo, "t-user", project_id="p-user", goal_id="g-1")
    role_repo.create({"id": "r-user", "name": "UserRole", "scope": "workspace"})

    assert _ids(user_repo.get("u-other")) == ["u-other"]
    assert "u-main" in _ids(user_repo.get_workspace_users("ws-user"))

    user_repo.assign_to_ticket("u-other", "t-user", "ws-user")
    assert _ids(user_repo.get_assigned_tickets("u-other", "ws-user")) == ["t-user"]
    user_repo.unassign_from_ticket("u-other", "t-user", "ws-user")
    assert user_repo.get_assigned_tickets("u-other", "ws-user") == []

    user_repo.set_ticket_creator("u-other", "t-user", "ws-user")
    assert _ids(user_repo.get_created_tickets("u-other", "ws-user")) == ["t-user"]

    user_repo.assign_role("u-other", "r-user", "ws-user")
    assert _ids(user_repo.get_roles("u-other", "ws-user")) == ["r-user"]
    assert set(_ids(user_repo.get_workspace_users("ws-user"))) == {"u-main", "u-other"}

    user_repo.revoke_role("u-other", "r-user", "ws-user")
    assert user_repo.get_roles("u-other", "ws-user") == []

    user_repo.delete("u-other")
    assert user_repo.get("u-other") == []
