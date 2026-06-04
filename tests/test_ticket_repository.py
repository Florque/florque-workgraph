import pytest
from florque_workgraph.repositories import (
    GoalRepository,
    ProjectRepository,
    StrategyRepository,
    TicketRepository,
    TimeboxRepository,
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
        "timebox": lambda workspace_id: TimeboxRepository(florque_workgraph, workspace_id),
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

def test_ticket_repository_methods(repos):
    # Setup
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]
    _create_workspace(workspace_repo, user_repo, workspace_id="ws-ticket", creator_id="u-ticket-owner")
    _create_user(user_repo, "u-ticket-member")

    project_repo = repos["project"]("ws-ticket")
    vision_repo = repos["vision"]("ws-ticket")
    strategy_repo = repos["strategy"]("ws-ticket")
    goal_repo = repos["goal"]("ws-ticket")
    ticket_repo = repos["ticket"]("ws-ticket")
    timebox_repo = repos["timebox"]("ws-ticket")

    _create_project(project_repo, "p-a")
    _create_project(project_repo, "p-b")
    _create_vision(vision_repo, "v-1", "p-a")
    _create_strategy(strategy_repo, "s-1", "v-1")
    _create_goal(goal_repo, "g-1", "s-1")

    timebox_repo.create(
        {
            "id": "tb-1",
            "name": "Sprint 1",
            "start_date": "2026-01-01",
            "end_date": "2026-01-15",
            "status": "planned",
        }
    )

    # Tests
    _create_ticket(ticket_repo, "t-parent", project_id="p-a", goal_id="g-1")
    _create_ticket(ticket_repo, "t-child", project_id="p-a", parent_id="t-parent")
    _create_ticket(ticket_repo, "t-dep", project_id="p-a", goal_id="g-1")
    _create_ticket(ticket_repo, "t-rel", project_id="p-a", goal_id="g-1")

    assert _ids(ticket_repo.get("t-parent")) == ["t-parent"]
    assert set(_ids(ticket_repo.get_all())) == {"t-parent", "t-child", "t-dep", "t-rel"}
    assert _ids(ticket_repo.get_subtasks("t-parent")) == ["t-child"]
    assert _ids(ticket_repo.get_parent_tickets("t-child")) == ["t-parent"]
    assert _ids(ticket_repo.get_all_subtickets("t-parent")) == ["t-child"]

    ticket_repo.add_subtask("t-parent", "t-dep")
    assert set(_ids(ticket_repo.get_subtasks("t-parent"))) == {"t-child", "t-dep"}
    ticket_repo.remove_subtask("t-parent", "t-dep")
    assert _ids(ticket_repo.get_subtasks("t-parent")) == ["t-child"]

    ticket_repo.add_dependency("t-child", "t-dep")
    assert _ids(ticket_repo.get_dependencies("t-child")) == ["t-dep"]
    assert _ids(ticket_repo.get_dependents("t-dep")) == ["t-child"]
    dep_edges = ticket_repo.get_edges_by_type(["t-child"], "depend_on")
    assert any(edge[0] == "t-child" and edge[2] == "t-dep" for edge in dep_edges)
    ticket_repo.remove_dependency("t-child", "t-dep")
    assert ticket_repo.get_dependencies("t-child") == []

    ticket_repo.add_relation("t-child", "t-rel")
    assert _ids(ticket_repo.get_related("t-child")) == ["t-rel"]
    rel_edges = ticket_repo.get_edges_by_type(["t-child"], "RELATES_TO")
    assert any(edge[0] == "t-child" and edge[2] == "t-rel" for edge in rel_edges)
    ticket_repo.remove_relation("t-child", "t-rel")
    assert ticket_repo.get_related("t-child") == []

    ticket_repo.assign_user("u-ticket-member", "t-child")
    assert _ids(ticket_repo.get_assigned_users("t-child")) == ["u-ticket-member"]
    ticket_repo.unassign_user("u-ticket-member", "t-child")
    assert ticket_repo.get_assigned_users("t-child") == []

    ticket_repo.set_creator("u-ticket-owner", "t-child")
    assert _ids(ticket_repo.get_creator("t-child")) == ["u-ticket-owner"]

    ticket_repo.schedule("t-child", "tb-1")
    assert _ids(ticket_repo.get_scheduled_timebox("t-child")) == ["tb-1"]

    updated = ticket_repo.update(
        "t-child",
        {
            "title": "Updated Child",
            "description": "updated",
            "status": "in_progress",
            "project_id": "p-b",
        },
    )
    assert updated[0][0].properties["title"] == "Updated Child"
    assert updated[0][0].properties["project_id"] == "p-b"
    assert "t-child" in _ids(project_repo.get_tickets("p-b"))

    assert ticket_repo.get_edges_by_type([], "SUBTASK") == []

    ticket_repo.delete("t-child")
    assert ticket_repo.get("t-child") == []
