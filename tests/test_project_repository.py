import pytest
from florque_workgraph.repositories import (
    GoalRepository,
    ProjectRepository,
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

def test_project_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]
    _create_workspace(workspace_repo, user_repo, workspace_id="ws-project", creator_id="u-project")

    project_repo = repos["project"]("ws-project")
    ticket_repo = repos["ticket"]("ws-project")
    vision_repo = repos["vision"]("ws-project")
    strategy_repo = repos["strategy"]("ws-project")
    goal_repo = repos["goal"]("ws-project")

    _create_project(project_repo, "p-1")
    assert _ids(project_repo.get("p-1")) == ["p-1"]
    assert _ids(project_repo.get_all()) == ["p-1"]

    project_repo.add_to_workspace("p-1")
    assert _ids(workspace_repo.get_projects("ws-project")) == ["p-1"]

    updated = project_repo.update("p-1", {"name": "Updated Project", "description": "new desc"})
    assert updated[0][0].properties["name"] == "Updated Project"
    assert updated[0][0].properties["description"] == "new desc"

    _create_vision(vision_repo, "v-1", "p-1")
    _create_strategy(strategy_repo, "s-1", "v-1")
    _create_goal(goal_repo, "g-1", "s-1")
    _create_ticket(ticket_repo, "t-1", project_id="p-1", goal_id="g-1")
    _create_ticket(ticket_repo, "t-2", project_id="p-1", goal_id="g-1")
    
    project_repo.add_ticket("t-2", "p-1")
    assert set(_ids(project_repo.get_tickets("p-1"))) == {"t-1", "t-2"}

    project_repo.remove_ticket("t-2", "p-1")
    assert _ids(project_repo.get_tickets("p-1")) == ["t-1"]

    project_repo.remove_from_workspace("p-1")
    assert workspace_repo.get_projects("ws-project") == []

    project_repo.delete("p-1")
    assert project_repo.get("p-1") == []
