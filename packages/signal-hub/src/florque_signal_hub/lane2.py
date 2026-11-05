"""Lane 2: association for channel and email input (spec 6.4). Deferred to M4; interface only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from florque_signal_hub.envelope import Observation

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Association:
    node_id: str | None
    confidence: Confidence
    candidates: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class Associator(Protocol):
    """Explicit hints first, then candidate retrieval in the mapped project, then a constrained LLM choice."""

    def associate(self, obs: Observation, project_id: str) -> Association: ...


class NoAssociator:
    """Default until M4: everything without a registered code goes to the inbox."""

    def associate(self, obs: Observation, project_id: str) -> Association:
        return Association(node_id=None, confidence="low")
