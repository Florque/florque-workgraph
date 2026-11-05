"""Pipeline steps 1-3: class and kind, slot types / enums / required fields, LinkML rules."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from florque_graph_core.errors import ErrorCode, GraphError
from florque_graph_core.ontology.model import (
    SYSTEM_FIELDS,
    ClassSpec,
    Condition,
    OntologyModel,
    SlotSpec,
)

DATETIME_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime(DATETIME_FMT)


def parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def resolve_class(model: OntologyModel, name: str) -> ClassSpec:
    spec = model.cls(name)
    if spec is None or spec.abstract:
        raise GraphError(
            ErrorCode.ONTOLOGY_VIOLATION,
            f"Unknown or abstract class {name!r}",
            hint=f"Use one of: {', '.join(c.name for c in model.concrete())}",
        )
    return spec


def check_kind(spec: ClassSpec, kind: Any) -> None:
    if spec.kinds is None:
        if kind is not None:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION, f"{spec.name} has no kinds", hint="Remove 'kind'."
            )
        return
    if kind is None:
        if spec.kind_required:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"{spec.name} requires a kind",
                hint=f"Set kind to one of: {', '.join(spec.kinds)}",
            )
        return
    if kind not in spec.kinds:
        raise GraphError(
            ErrorCode.ONTOLOGY_VIOLATION,
            f"Unknown kind {kind!r} for {spec.name}",
            hint=f"Use one of: {', '.join(spec.kinds)}",
        )


def _coerce(slot: SlotSpec, value: Any) -> Any:
    t = slot.base_type
    if t in ("str",) and isinstance(value, str):
        return value
    if t == "enum" and isinstance(value, str) and slot.enum_values and value in slot.enum_values:
        return value
    if t == "int" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if t == "float" and isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if t == "bool" and isinstance(value, bool):
        return value
    if t == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                pass
    if t == "datetime":
        if isinstance(value, datetime):
            return format_datetime(value)
        if isinstance(value, str):
            try:
                return format_datetime(parse_datetime(value))
            except ValueError:
                pass
    expected = f"one of {list(slot.enum_values or ())}" if t == "enum" else t
    raise GraphError(
        ErrorCode.ONTOLOGY_VIOLATION,
        f"Field {slot.name!r}: invalid value {value!r}",
        hint=f"Expected {expected}.",
        details={"field": slot.name},
    )


def validate_fields(
    spec: ClassSpec, props: Mapping[str, Any], *, allow_null: bool
) -> dict[str, Any]:
    """Type-check and normalize the given fields. Unknown and system fields are rejected."""
    out: dict[str, Any] = {}
    for key, value in props.items():
        if key in SYSTEM_FIELDS:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"Field {key!r} is managed by the engine",
                hint=f"Remove {key!r} from the request.",
            )
        if key in spec.edges:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"{key!r} is an edge, not a field",
                hint="Pass edges in 'edges' (or use link); pass the parent as parent_id.",
            )
        slot = spec.slots.get(key)
        if slot is None:
            raise GraphError(
                ErrorCode.ONTOLOGY_VIOLATION,
                f"{spec.name} has no field {key!r}",
                hint=f"Known fields: {', '.join(sorted(k for k, s in spec.slots.items() if s.owner != 'system'))}",
            )
        if value is None:
            if not allow_null:
                continue
            out[key] = None
            continue
        if slot.multivalued:
            items = value if isinstance(value, list) else [value]
            out[key] = [_coerce(slot, v) for v in items]
        else:
            out[key] = _coerce(slot, value)
    return out


def _present(props: Mapping[str, Any], key: str) -> bool:
    v = props.get(key)
    return v is not None and v != "" and v != []


def check_required(spec: ClassSpec, props: Mapping[str, Any]) -> None:
    missing = [
        n
        for n, s in spec.slots.items()
        if s.required and s.owner != "system" and not _present(props, n)
    ]
    if missing:
        raise GraphError(
            ErrorCode.ONTOLOGY_VIOLATION,
            f"{spec.name} is missing required field(s): {', '.join(missing)}",
            hint=f"Provide {', '.join(missing)}.",
            details={"missing": missing},
        )


def _cond_holds(props: Mapping[str, Any], key: str, cond: Condition) -> bool:
    if cond.required and not _present(props, key):
        return False
    if cond.equals_string is not None and props.get(key) != cond.equals_string:
        return False
    return not (cond.equals_number is not None and props.get(key) != cond.equals_number)


def check_rules(spec: ClassSpec, props: Mapping[str, Any]) -> None:
    for rule in spec.rules:
        if all(_cond_holds(props, k, c) for k, c in rule.pre.items()):
            failing = [k for k, c in rule.post.items() if not _cond_holds(props, k, c)]
            if failing:
                raise GraphError(
                    ErrorCode.ONTOLOGY_VIOLATION,
                    f"{rule.description or 'Rule failed'} Missing or invalid: {', '.join(failing)}",
                    hint=f"Provide {', '.join(failing)}.",
                    details={"fields": failing},
                )
