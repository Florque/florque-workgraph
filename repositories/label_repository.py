from typing import Any

from session import GraphManager
from queries import (
    CREATE_LABEL,
    GET_LABEL,
    GET_ALL_LABELS,
    UPDATE_LABEL,
    DELETE_LABEL,
    CREATE_LABELED_RELATIONSHIP,
    DELETE_LABELED_RELATIONSHIP,
    GET_LABELS_FOR_NODE
)


class LabelRepository:
    """
    Workspace-scoped domain operations for Label nodes and their relationships.
    """

    def __init__(self, db: GraphManager, workspace_id: str) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def _p(self, **kwargs) -> dict:
        """Return kwargs merged with the mandatory workspace_id."""
        return {"workspace_id": self.workspace_id, **kwargs}

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    def create(self, label_data: dict) -> list[Any]:
        """Create a Label node."""
        params = self._p(**label_data)
        return self.db.execute_write(CREATE_LABEL, params)

    def get(self, label_id: str) -> list[Any]:
        """Return a single Label node by id."""
        return self.db.execute(GET_LABEL, self._p(id=label_id))

    def get_all(self, project_id: str) -> list[Any]:
        """Return all Label nodes in this project."""
        return self.db.execute(GET_ALL_LABELS, self._p(project_id=project_id))

    def update(self, label_id: str, updates: dict) -> list[Any]:
        """Update fields on a Label node."""
        params = self._p(id=label_id, **updates)
        return self.db.execute_write(UPDATE_LABEL, params)

    def delete(self, label_id: str, project_id: str) -> None:
        """Detach-delete a Label node."""
        self.db.execute_write(DELETE_LABEL, self._p(id=label_id, project_id=project_id))

    # ── Edge Management ────────────────────────────────────────────────────────

    def add_label_to_node(self, label_id: str, node_id: str) -> None:
        """Create a LABELED relationship from a node (Ticket, Goal, Strategy) to a Label."""
        params = self._p(label_id=label_id, node_id=node_id)
        self.db.execute_write(CREATE_LABELED_RELATIONSHIP, params)

    def remove_label_from_node(self, label_id: str, node_id: str) -> None:
        """Delete the LABELED relationship between a node and a Label."""
        params = self._p(label_id=label_id, node_id=node_id)
        self.db.execute_write(DELETE_LABELED_RELATIONSHIP, params)

    def get_labels_for_node(self, node_id: str) -> list[Any]:
        """Return all Labels for a given node."""
        return self.db.execute(GET_LABELS_FOR_NODE, self._p(node_id=node_id))
