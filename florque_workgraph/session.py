import logging
import os
from typing import Any

import mgclient

from .queries import CONSTRAINTS

logger = logging.getLogger(__name__)

GRAPH_HOST = os.getenv("GRAPH_DB_HOST", "localhost")
GRAPH_PORT = int(os.getenv("GRAPH_DB_PORT", "7687"))


class GraphManager:
    """
    Connection layer for Memgraph.

    Responsibilities:
    - Manage the bolt connection via mgclient
    - Execute parameterized read/write Cypher queries
    - Handle transactions (commit / rollback)
    """

    def __init__(self, host: str = GRAPH_HOST, port: int = GRAPH_PORT) -> None:
        self._conn = mgclient.connect(host=host, port=port)
        logger.info("GraphManager connected to %s:%s", host, port)

    # ── Query execution ────────────────────────────────────────────────────────

    def execute(self, query: str, params: dict | None = None) -> list[Any]:
        """Execute a read query and return all rows."""
        cursor = self._conn.cursor()
        cursor.execute(query, params or {})
        return cursor.fetchall()

    def execute_write(self, query: str, params: dict | None = None) -> list[Any]:
        """Execute a write query, commit, and return any returned rows."""
        cursor = self._conn.cursor()
        cursor.execute(query, params or {})
        rows = cursor.fetchall()
        self._conn.commit()
        return rows

    # ── Schema bootstrap ───────────────────────────────────────────────────────

    def apply_constraints(self) -> None:
        """Idempotently create all uniqueness constraints."""
        for statement in CONSTRAINTS:
            try:
                self.execute_write(statement)
                logger.debug("Applied constraint: %s", statement)
            except Exception as exc:  # constraint may already exist
                logger.debug("Constraint skipped (%s): %s", exc, statement)

    # ── Context manager support ────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "GraphManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class UnitOfWork:
    """
    Optional transactional unit-of-work wrapper.
    Use as a context manager when multiple writes must be atomic.
    """

    def __init__(self, manager: GraphManager) -> None:
        self._manager = manager
        self._cursor = None

    def __enter__(self):
        self._cursor = self._manager._conn.cursor()
        return self._cursor

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self._manager._conn.rollback()
            logger.warning("UnitOfWork rolled back due to %s", exc_type)
        else:
            self._manager._conn.commit()
