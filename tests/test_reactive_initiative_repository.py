import pytest
from florque_workgraph.repositories.reactive_initiative_repository import ReactiveInitiativeRepository
from florque_workgraph.repositories.project_repository import ProjectRepository
from florque_workgraph.repositories.ticket_repository import TicketRepository
from florque_workgraph.repositories.workspace_repository import WorkspaceRepository
from florque_workgraph.repositories.user_repository import UserRepository
from florque_workgraph.session import GraphManager
import uuid

# Helper to extract IDs from query results
def _ids(rows):
    return [row[0].properties["id"] for row in rows]

# Fixture to connect to Memgraph, runs once per session
@pytest.fixture(scope="session")
def db_connection():
    try:
        db = GraphManager()
        db.apply_constraints()
        yield db
        db.close()
    except Exception as exc:
        pytest.skip(f"Memgraph is not reachable: {exc}")

# Fixture to clean the graph before each test
@pytest.fixture(autouse=True)
def clean_graph(db_connection):
    db_connection.execute_write("MATCH (n) DETACH DELETE n")

# Test data
WORKSPACE_ID = "test-workspace"
PROJECT_ID = "test-project"
INITIATIVE_ID_1 = str(uuid.uuid4())
INITIATIVE_ID_2 = str(uuid.uuid4())
TICKET_ID_1 = str(uuid.uuid4())
TICKET_ID_2 = str(uuid.uuid4())

@pytest.fixture
def setup_repositories(db_connection):
    """Setup repositories and initial data for tests."""
    # Create repositories
    user_repo = UserRepository(db_connection)
    workspace_repo = WorkspaceRepository(db_connection)
    project_repo = ProjectRepository(db_connection, WORKSPACE_ID)
    initiative_repo = ReactiveInitiativeRepository(db_connection, WORKSPACE_ID)
    ticket_repo = TicketRepository(db_connection, WORKSPACE_ID)
    
    # Create base data
    user_repo.create({"id": "test-user", "name": "Test User", "email": "test@test.com"})
    workspace_repo.create({"id": WORKSPACE_ID, "name": "Test Workspace", "creator_user_id": "test-user"})
    project_repo.create({"id": PROJECT_ID, "name": "Test Project", "description": "A project for testing"})
    
    return initiative_repo, ticket_repo

def test_create_and_get_initiative(setup_repositories):
    """Test creating and retrieving a ReactiveInitiative."""
    initiative_repo, _ = setup_repositories
    
    # Test creation
    initiative_data = {
        "id": INITIATIVE_ID_1,
        "title": "Test Initiative 1",
        "description": "Description for initiative 1",
        "project_id": PROJECT_ID
    }
    initiative_repo.create(initiative_data)
    
    # Test get by ID
    result = initiative_repo.get(INITIATIVE_ID_1)
    assert len(result) == 1
    assert result[0][0].properties["id"] == INITIATIVE_ID_1
    assert result[0][0].properties["title"] == "Test Initiative 1"
    
    # Test get by project
    result_by_project = initiative_repo.get_by_project(PROJECT_ID)
    assert len(result_by_project) == 1
    assert _ids(result_by_project) == [INITIATIVE_ID_1]

def test_update_initiative(setup_repositories):
    """Test updating a ReactiveInitiative."""
    initiative_repo, _ = setup_repositories
    
    # Create initial initiative
    initiative_data = {"id": INITIATIVE_ID_1, "title": "Original Title", "description": "Original Desc", "project_id": PROJECT_ID}
    initiative_repo.create(initiative_data)
    
    # Update title and description
    updates = {"title": "Updated Title", "description": "Updated Desc"}
    initiative_repo.update(INITIATIVE_ID_1, updates)
    
    # Verify update
    result = initiative_repo.get(INITIATIVE_ID_1)
    assert result[0][0].properties["title"] == "Updated Title"
    assert result[0][0].properties["description"] == "Updated Desc"

def test_archive_and_filter_initiatives(setup_repositories):
    """Test archiving an initiative and filtering by archived status."""
    initiative_repo, _ = setup_repositories
    
    # Create two initiatives
    initiative_repo.create({"id": INITIATIVE_ID_1, "title": "Initiative 1", "project_id": PROJECT_ID})
    initiative_repo.create({"id": INITIATIVE_ID_2, "title": "Initiative 2", "project_id": PROJECT_ID})

    # Archive one initiative
    initiative_repo.set_archived_status(INITIATIVE_ID_2, True)
    
    # Check that get_by_project (default) excludes archived
    unarchived_results = initiative_repo.get_by_project(PROJECT_ID)
    assert _ids(unarchived_results) == [INITIATIVE_ID_1]
    
    # Check that get_by_project (including archived) returns both
    all_results = initiative_repo.get_by_project(PROJECT_ID, include_archived=True)
    assert set(_ids(all_results)) == {INITIATIVE_ID_1, INITIATIVE_ID_2}

def test_delete_initiative(setup_repositories):
    """Test deleting a ReactiveInitiative."""
    initiative_repo, _ = setup_repositories
    initiative_repo.create({"id": INITIATIVE_ID_1, "title": "To Be Deleted", "project_id": PROJECT_ID})
    
    # Confirm it exists
    assert len(initiative_repo.get(INITIATIVE_ID_1)) == 1
    
    # Delete and confirm it's gone
    initiative_repo.delete(INITIATIVE_ID_1)
    assert len(initiative_repo.get(INITIATIVE_ID_1)) == 0

def test_get_tickets_for_initiative(setup_repositories):
    """Test linking tickets and retrieving them via get_tickets."""
    initiative_repo, ticket_repo = setup_repositories
    
    # Create an initiative
    initiative_repo.create({"id": INITIATIVE_ID_1, "title": "Initiative with Tickets", "project_id": PROJECT_ID})
    
    # Create tickets executing the initiative
    ticket_repo.create_ticket_executing_reactive_initiative({
        "id": TICKET_ID_1, "title": "Ticket 1", "project_id": PROJECT_ID, "reactive_initiative_id": INITIATIVE_ID_1
    })
    ticket_repo.create_ticket_executing_reactive_initiative({
        "id": TICKET_ID_2, "title": "Ticket 2", "project_id": PROJECT_ID, "reactive_initiative_id": INITIATIVE_ID_1
    })
    
    # Retrieve and verify tickets
    tickets = initiative_repo.get_tickets(INITIATIVE_ID_1)
    assert len(tickets) == 2
    assert set(_ids(tickets)) == {TICKET_ID_1, TICKET_ID_2}
