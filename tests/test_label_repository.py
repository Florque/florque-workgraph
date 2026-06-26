import pytest
from unittest.mock import MagicMock
from florque_workgraph.repositories.label_repository import LabelRepository
from florque_workgraph.queries import queries

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def label_repo(mock_db):
    return LabelRepository(mock_db, "test_workspace")

def test_create(label_repo):
    label_data = {"id": "label1", "title": "Test Label"}
    label_repo.create(label_data)
    label_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_LABEL,
        {'workspace_id': 'test_workspace', 'id': 'label1', 'title': 'Test Label'}
    )

def test_get(label_repo):
    label_repo.get("label1")
    label_repo.db.execute.assert_called_once_with(
        queries.GET_LABEL,
        {'workspace_id': 'test_workspace', 'id': 'label1'}
    )

def test_get_all(label_repo):
    label_repo.get_all()
    label_repo.db.execute.assert_called_once_with(
        queries.GET_ALL_LABELS,
        {'workspace_id': 'test_workspace'}
    )

def test_update(label_repo):
    updates = {"title": "New Title"}
    label_repo.update("label1", updates)
    label_repo.db.execute_write.assert_called_once_with(
        queries.UPDATE_LABEL,
        {'workspace_id': 'test_workspace', 'id': 'label1', 'title': 'New Title'}
    )

def test_delete(label_repo):
    label_repo.delete("label1")
    label_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_LABEL,
        {'workspace_id': 'test_workspace', 'id': 'label1'}
    )

def test_add_label_to_node(label_repo):
    label_repo.add_label_to_node("label1", "node1")
    label_repo.db.execute_write.assert_called_once_with(
        queries.CREATE_LABELED_RELATIONSHIP,
        {'workspace_id': 'test_workspace', 'label_id': 'label1', 'node_id': 'node1'}
    )

def test_remove_label_from_node(label_repo):
    label_repo.remove_label_from_node("label1", "node1")
    label_repo.db.execute_write.assert_called_once_with(
        queries.DELETE_LABELED_RELATIONSHIP,
        {'workspace_id': 'test_workspace', 'label_id': 'label1', 'node_id': 'node1'}
    )

def test_get_labels_for_node(label_repo):
    label_repo.get_labels_for_node("node1")
    label_repo.db.execute.assert_called_once_with(
        queries.GET_LABELS_FOR_NODE,
        {'workspace_id': 'test_workspace', 'node_id': 'node1'}
    )
