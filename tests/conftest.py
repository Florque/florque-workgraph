"""Shared fixtures. Graph tests run on the memory store, and on Neo4j when one is reachable
(NEO4J_URI/NEO4J_PASSWORD set, or Docker available for testcontainers)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from florque_graph_core import GraphCore, Principal
from florque_graph_core.store.memory import MemoryStore
from florque_signal_hub import SignalHub, SQLiteHubStore
from florque_workgraph_domain import build_core, load

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolated_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests never read the developer's credentials or FLORQUE_* settings."""
    for var in list(os.environ):
        if var.startswith("FLORQUE_") and var not in ("FLORQUE_TEST_NEO4J",):
            monkeypatch.delenv(var)
    monkeypatch.setenv("FLORQUE_CREDENTIALS", str(tmp_path_factory.mktemp("creds") / "c.json"))


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


ADMIN = Principal("alice", {"*": "admin"}, can_create_projects=True)


@pytest.fixture(scope="session")
def model():
    return load()


def _docker_available() -> bool:
    try:
        import docker  # type: ignore[import-not-found]

        docker.from_env().ping()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def neo4j_conn() -> Iterator[tuple[str, str, str] | None]:
    if os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD"):
        yield (
            os.environ["NEO4J_URI"],
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ["NEO4J_PASSWORD"],
        )
        return
    if os.environ.get("FLORQUE_TEST_NEO4J", "auto") == "off" or not _docker_available():
        yield None
        return
    from testcontainers.neo4j import Neo4jContainer

    with Neo4jContainer("neo4j:5.26.0") as c:
        yield c.get_connection_url(), c.username, c.password


def _make_graph_store(kind: str, neo4j_conn: tuple[str, str, str] | None) -> Any:
    if kind == "memory":
        return MemoryStore()
    if neo4j_conn is None:
        pytest.skip("Neo4j not available (set NEO4J_URI/NEO4J_PASSWORD or start Docker)")
    from florque_graph_core.store.neo4j import Neo4jStore

    a = Neo4jStore(*neo4j_conn)
    with a._driver.session() as s:  # noqa: SLF001 - test cleanup
        s.run("MATCH (n) DETACH DELETE n").consume()
    return a


@pytest.fixture(params=["memory", pytest.param("neo4j", marks=pytest.mark.neo4j)])
def graph_store(request: pytest.FixtureRequest, neo4j_conn: Any) -> Iterator[Any]:
    a = _make_graph_store(request.param, neo4j_conn)
    yield a
    a.close()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def core(graph_store: Any, clock: Clock) -> GraphCore:
    return build_core(graph_store, clock=clock)


@pytest.fixture
def hub(core: GraphCore, clock: Clock) -> Iterator[SignalHub]:
    store = SQLiteHubStore()
    h = SignalHub(core, store, clock=clock)
    core.register_hook(h.series_code_hook)
    yield h
    store.close()


KR_PROPS = {
    "kind": "key_result",
    "title": "DAU at least 1000",
    "series_code": "dau",
    "comparator": ">=",
    "target_value": 1000,
    "unit": "users",
    "reducer": "last",
    "window_start": "2026-11-01",
    "window_end": "2026-11-30",
    "baseline_value": 200,
    "status": "active",
}


class World:
    """A small seeded project."""

    def __init__(self, core: GraphCore, hub: SignalHub | None = None) -> None:
        self.core = core
        self.project = core.create(ADMIN, "Project", {"title": "Florque"})["node"]["id"]
        self.objective = core.create(
            ADMIN, "Goal", {"kind": "objective", "title": "Grow usage"}, self.project
        )["node"]["id"]
        if hub is not None:
            hub.add_source(ADMIN, "metrics", "sensor")
            hub.add_sensor(ADMIN, "dau", self.project, "users", source_id="metrics")
        self.kr = core.create(ADMIN, "Goal", KR_PROPS, self.objective)["node"]["id"]
        self.initiative = core.create(
            ADMIN,
            "WorkItem",
            {"kind": "initiative", "title": "Onboarding"},
            self.project,
            edges=[{"type": "serves", "to": self.kr}],
        )["node"]["id"]
        self.epic = core.create(
            ADMIN, "WorkItem", {"kind": "epic", "title": "Signup flow"}, self.initiative
        )["node"]["id"]
        self.task = core.create(
            ADMIN, "WorkItem", {"kind": "task", "title": "Email verification"}, self.epic
        )["node"]["id"]


@pytest.fixture
def world(core: GraphCore, hub: SignalHub) -> World:
    return World(core, hub)
