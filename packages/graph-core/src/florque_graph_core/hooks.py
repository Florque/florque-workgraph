"""Policy hooks registered by the host (spec 5.1). A hook raises GraphError to refuse a write."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from florque_graph_core.ontology.model import ClassSpec, OntologyModel
from florque_graph_core.principal import Principal
from florque_graph_core.store.base import StoreTx


@dataclass
class WriteContext:
    op: str  # create | update | supersede
    principal: Principal
    role: str | None
    cls: ClassSpec
    props: dict[str, Any]  # the full resulting field values
    patch: dict[str, Any]  # the fields this write sets
    existing: dict[str, Any] | None
    model: OntologyModel
    tx: StoreTx
    project_id: str | None = None
    tenant_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


Hook = Callable[[WriteContext], None]
