"""Error codes and the {ok, data} / {ok: false, error} response envelope (spec 5.5)."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    ONTOLOGY_VIOLATION = "ONTOLOGY_VIOLATION"
    PARENT_RULE = "PARENT_RULE"
    REQUIRED_EDGE = "REQUIRED_EDGE"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    OWNERSHIP = "OWNERSHIP"
    DUPLICATE_EXACT = "DUPLICATE_EXACT"
    DUPLICATE_SIMILAR = "DUPLICATE_SIMILAR"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    UNAUTHENTICATED = "UNAUTHENTICATED"


class GraphError(Exception):
    """A rejected operation. The hint tells the caller what to change."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        hint: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "message": self.message,
            "hint": self.hint,
            "details": self.details,
        }


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(err: GraphError) -> dict[str, Any]:
    return {"ok": False, "error": err.to_dict()}


def envelope(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Call fn and wrap its result or GraphError in the response envelope."""
    try:
        return ok(fn(*args, **kwargs))
    except GraphError as e:
        return fail(e)
