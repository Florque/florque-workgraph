"""The acting identity passed with every call (spec 5.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

WILDCARD = "*"


@dataclass(frozen=True)
class Principal:
    actor_id: str
    roles: Mapping[str, str] = field(default_factory=dict)
    """Role per project id. The key "*" applies to every project."""
    is_agent: bool = False
    can_create_projects: bool = False

    def role_in(self, project_id: str | None) -> str | None:
        if project_id is not None and project_id in self.roles:
            return self.roles[project_id]
        return self.roles.get(WILDCARD)

    def any_role(self, wanted: set[str]) -> bool:
        return any(r in wanted for r in self.roles.values())
