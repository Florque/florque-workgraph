import pytest

from florque_workgraph.repositories import (
    CapabilityRepository,
    MembershipRepository,
    ProjectRepository,
    RoleRepository,
    TicketRepository,
    TimeboxRepository,
    UserRepository,
    WorkspaceRepository,
)
from florque_workgraph.session import GraphManager


def _ids(rows):
    return [row[0].properties["id"] for row in rows]


@pytest.fixture(scope="session")
def florque_workgraph():
    # To run a test instance of Memgraph:
    # docker run --name memgraph-test -p 7666:7687 --rm memgraph/memgraph
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
        "role": lambda workspace_id: RoleRepository(florque_workgraph, workspace_id),
        "capability": CapabilityRepository(florque_workgraph),
        "membership": MembershipRepository(florque_workgraph),
    }


def _create_user(user_repo, user_id, name=None):
    user_repo.create({"id": user_id, "name": name or user_id, "email": f"{user_id}@example.com"})


def _create_workspace(workspace_repo, user_repo, workspace_id="ws-1", creator_id="u-creator"):
    _create_user(user_repo, creator_id)
    workspace_repo.create({"id": workspace_id, "name": workspace_id, "creator_user_id": creator_id})


def _create_project(project_repo, project_id="p-1"):
    project_repo.create({"id": project_id, "name": project_id, "description": f"{project_id} desc"})


def _create_ticket(ticket_repo, ticket_id, project_id=None, parent_id=None):
    ticket_repo.create(
        {
            "id": ticket_id,
            "title": f"title {ticket_id}",
            "description": f"desc {ticket_id}",
            "status": "todo",
            "project_id": project_id,
            "parent_id": parent_id,
        }
    )


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


def test_project_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-project", creator_id="u-project")

    project_repo = repos["project"]("ws-project")
    ticket_repo = repos["ticket"]("ws-project")

    _create_project(project_repo, "p-1")
    assert _ids(project_repo.get("p-1")) == ["p-1"]
    assert _ids(project_repo.get_all()) == ["p-1"]

    project_repo.add_to_workspace("p-1")
    assert _ids(workspace_repo.get_projects("ws-project")) == ["p-1"]

    updated = project_repo.update("p-1", {"name": "Updated Project", "description": "new desc"})
    assert updated[0][0].properties["name"] == "Updated Project"
    assert updated[0][0].properties["description"] == "new desc"

    _create_ticket(ticket_repo, "t-1", project_id="p-1")
    _create_ticket(ticket_repo, "t-2", project_id=None)
    project_repo.add_ticket("t-2", "p-1")
    assert set(_ids(project_repo.get_tickets("p-1"))) == {"t-1", "t-2"}

    project_repo.remove_ticket("t-2", "p-1")
    assert _ids(project_repo.get_tickets("p-1")) == ["t-1"]

    project_repo.remove_from_workspace("p-1")
    assert workspace_repo.get_projects("ws-project") == []

    project_repo.delete("p-1")
    assert project_repo.get("p-1") == []


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
    assert set(_ids(role_repo.get_all())) >= {"r-ws", "r-pr"}
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


def test_ticket_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-ticket", creator_id="u-ticket-owner")
    _create_user(user_repo, "u-ticket-member")

    project_repo = repos["project"]("ws-ticket")
    ticket_repo = repos["ticket"]("ws-ticket")
    timebox_repo = repos["timebox"]("ws-ticket")

    _create_project(project_repo, "p-a")
    _create_project(project_repo, "p-b")

    timebox_repo.create(
        {
            "id": "tb-1",
            "name": "Sprint 1",
            "start_date": "2026-01-01",
            "end_date": "2026-01-15",
            "status": "planned",
        }
    )

    _create_ticket(ticket_repo, "t-parent", project_id="p-a")
    _create_ticket(ticket_repo, "t-child", project_id="p-a", parent_id="t-parent")
    _create_ticket(ticket_repo, "t-dep", project_id="p-a")
    _create_ticket(ticket_repo, "t-rel", project_id="p-a")

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


def test_timebox_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    _create_workspace(workspace_repo, user_repo, workspace_id="ws-timebox", creator_id="u-timebox-owner")

    project_repo = repos["project"]("ws-timebox")
    ticket_repo = repos["ticket"]("ws-timebox")
    timebox_repo = repos["timebox"]("ws-timebox")

    _create_project(project_repo, "p-timebox")
    _create_ticket(ticket_repo, "t-timebox", project_id="p-timebox")

    timebox_repo.create(
        {
            "id": "tb-main",
            "name": "Main",
            "start_date": "2026-02-01",
            "end_date": "2026-02-14",
            "status": "planned",
        }
    )

    assert _ids(timebox_repo.get("tb-main")) == ["tb-main"]
    assert _ids(timebox_repo.get_all()) == ["tb-main"]

    timebox_repo.schedule_ticket("t-timebox", "tb-main")
    assert _ids(timebox_repo.get_scheduled_tickets("tb-main")) == ["t-timebox"]
    assert _ids(timebox_repo.get_tickets("tb-main")) == ["t-timebox"]

    timebox_repo.delete("tb-main")
    assert timebox_repo.get("tb-main") == []


def test_user_repository_methods(repos):
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]

    _create_user(user_repo, "u-main")
    _create_user(user_repo, "u-other")

    workspace_repo.create({"id": "ws-user", "name": "ws-user", "creator_user_id": "u-main"})

    project_repo = repos["project"]("ws-user")
    ticket_repo = repos["ticket"]("ws-user")
    role_repo = repos["role"]("ws-user")

    _create_project(project_repo, "p-user")
    _create_ticket(ticket_repo, "t-user", project_id="p-user")
    role_repo.create({"id": "r-user", "name": "UserRole", "scope": "workspace"})

    assert _ids(user_repo.get("u-other")) == ["u-other"]
    assert _ids(user_repo.get_workspace_users("ws-user")) == ["u-main"]

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


def test_workspace_repository_methods(repos):
    capability_repo = repos["capability"]
    workspace_repo = repos["workspace"]
    user_repo = repos["user"]
    membership_repo = repos["membership"]

    capability_repo.create({"id": "cap-admin", "name": "admin:all", "description": "all"})
    _create_user(user_repo, "u-workspace-owner")

    workspace_repo.create({"id": "ws-main", "name": "Main WS", "creator_user_id": "u-workspace-owner"})

    assert _ids(workspace_repo.get("ws-main")) == ["ws-main"]
    assert _ids(workspace_repo.get_user_workspaces("u-workspace-owner")) == ["ws-main"]

    # creation bootstrap: membership for creator should exist
    membership = membership_repo.get_by_user_workspace("u-workspace-owner", "ws-main")
    assert _ids(membership) == ["u-workspace-owner:ws-main"]

    project_repo = repos["project"]("ws-main")
    ticket_repo = repos["ticket"]("ws-main")

    _create_project(project_repo, "p-main")
    project_repo.add_to_workspace("p-main")
    _create_ticket(ticket_repo, "t-main", project_id="p-main")

    assert _ids(workspace_repo.get_projects("ws-main")) == ["p-main"]
    assert _ids(workspace_repo.get_tickets("ws-main")) == ["t-main"]

    workspace_repo.delete("ws-main")
    assert workspace_repo.get("ws-main") == []
