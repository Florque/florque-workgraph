"""Startup conformance against the mixin contracts (spec 6.1).

The hub asks graph-core which classes carry Expectation and Observation and
verifies fields, types and owner annotations. It never names a work-graph class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

COMPATIBLE_MIXINS = SpecifierSet(">=0.1,<0.2")

# field -> (type, owner or None for "any")
EXPECTATION_FIELDS: dict[str, tuple[str, str | None]] = {
    "series_code": ("str", None),
    "comparator": ("enum", None),
    "target_value": ("float", None),
    "target_upper": ("float", None),
    "unit": ("str", None),
    "reducer": ("enum", None),
    "window_start": ("date", None),
    "window_end": ("date", None),
    "baseline_value": ("float", None),
    "outcome": ("enum", "evaluator"),
    "health": ("enum", "evaluator"),
    "last_value": ("float", "evaluator"),
    "last_observed_at": ("datetime", "evaluator"),
    "evaluated_at": ("datetime", "evaluator"),
}
OBSERVATION_FIELDS: dict[str, tuple[str, str | None]] = {
    "source": ("str", None),
    "observed_at": ("datetime", None),
    "series_code": ("str", None),
    "numeric_value": ("float", None),
    "unit": ("str", None),
    "aggregation": ("str", None),
    "period": ("str", None),
    "revision": ("int", None),
    "payload_ref": ("str", None),
    "kind": ("enum", None),
    "title": ("str", None),
}
OBSERVATION_KINDS = {"metric", "feedback", "incident", "update"}
COMPARATORS = {"<=", ">=", "between"}
REDUCERS = {"last", "mean", "max", "all_points"}
OUTCOMES = {"pending", "succeeded", "failed", "expired"}
HEALTH = {"on_track", "at_risk", "no_data"}


class ContractError(RuntimeError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("Mixin contract mismatch:\n- " + "\n- ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Contract:
    ontology_version: str
    mixins_version: str
    expectation_class: str
    observation_class: str
    observation_has_about: bool


def _check_fields(
    cls: str, fields: dict[str, Any], wanted: dict[str, tuple[str, str | None]], problems: list[str]
) -> None:
    for name, (typ, owner) in wanted.items():
        f = fields.get(name)
        if f is None:
            problems.append(f"{cls}.{name} is missing")
            continue
        if f["type"] != typ:
            problems.append(f"{cls}.{name} has type {f['type']}, expected {typ}")
        if owner and f.get("owner") != owner:
            problems.append(f"{cls}.{name} is owned by {f.get('owner')}, expected {owner}")


def verify_contract(describe: dict[str, Any]) -> Contract:
    problems: list[str] = []
    mv = describe.get("mixins_version")
    if not mv:
        problems.append("ontology declares no mixins_version")
    elif Version(mv) not in COMPATIBLE_MIXINS:
        problems.append(f"mixins_version {mv} outside compatible range {COMPATIBLE_MIXINS}")

    classes: dict[str, Any] = describe.get("classes", {})
    exp = [n for n, c in classes.items() if "Expectation" in c.get("mixins", [])]
    obs = [n for n, c in classes.items() if "Observation" in c.get("mixins", [])]
    if len(exp) != 1:
        problems.append(f"exactly one class must carry Expectation, found {exp}")
    if len(obs) != 1:
        problems.append(f"exactly one class must carry Observation, found {obs}")
    has_about = False
    if len(exp) == 1:
        fields = classes[exp[0]]["fields"]
        _check_fields(exp[0], fields, EXPECTATION_FIELDS, problems)
        for name, values in (
            ("comparator", COMPARATORS),
            ("reducer", REDUCERS),
            ("outcome", OUTCOMES),
            ("health", HEALTH),
        ):
            if name in fields and not values <= set(fields[name].get("enum", [])):
                problems.append(f"{exp[0]}.{name} must offer {sorted(values)}")
    if len(obs) == 1:
        c = classes[obs[0]]
        _check_fields(obs[0], c["fields"], OBSERVATION_FIELDS, problems)
        kinds = set(c.get("kinds", []))
        if not kinds >= OBSERVATION_KINDS:
            problems.append(f"{obs[0]} kinds must include {sorted(OBSERVATION_KINDS - kinds)}")
        has_about = "about" in c.get("edges", {})
        if not has_about:
            problems.append(f"{obs[0]} must offer an about edge")
    if problems:
        raise ContractError(problems)
    return Contract(
        ontology_version=describe["ontology_version"],
        mixins_version=str(mv),
        expectation_class=exp[0],
        observation_class=obs[0],
        observation_has_about=has_about,
    )
