"""Immutable, engine-friendly view of a LinkML ontology.

The loader resolves SchemaView once into these dataclasses; validation and the
graph stores only ever read this model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SYSTEM_FIELDS = (
    "id",
    "class",
    "project_id",
    "created_at",
    "updated_at",
    "version",
    "dedupe_key",
    "archived_dedupe_key",
)


@dataclass(frozen=True)
class SlotSpec:
    name: str
    base_type: str  # str | int | float | bool | date | datetime | enum
    enum_values: tuple[str, ...] | None = None
    enum_name: str | None = None
    required: bool = False
    multivalued: bool = False
    owner: str = "human"
    immutable: str | None = None  # None | "always" | a status value
    description: str = ""


@dataclass(frozen=True)
class EdgeSpec:
    slot: str
    rel_type: str
    targets: frozenset[str]  # concrete class names
    multivalued: bool
    properties: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class KindSpec:
    name: str
    allowed_parents: tuple[tuple[str, str | None], ...]  # (class, kind or None)
    requires: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class Condition:
    equals_string: str | None = None
    equals_number: float | None = None
    required: bool = False


@dataclass(frozen=True)
class RuleSpec:
    description: str
    pre: dict[str, Condition]
    post: dict[str, Condition]


@dataclass(frozen=True)
class ClassSpec:
    name: str
    abstract: bool
    ancestors: tuple[str, ...]
    mixins: tuple[str, ...]
    slots: dict[str, SlotSpec]
    edges: dict[str, EdgeSpec]
    kinds: dict[str, KindSpec] | None
    kind_required: bool
    allowed_parents: tuple[tuple[str, str | None], ...]  # used when kinds is None
    rules: tuple[RuleSpec, ...]
    root: bool = False
    scope: str = "project"  # project | global
    natural_key: tuple[str, ...] = ()
    dedupe_scope: str = "parent"
    merge: str = "additive"
    guidance: dict[str, str] = field(default_factory=dict)
    description: str = ""

    @property
    def labels(self) -> tuple[str, ...]:
        return (self.name, "Node", *self.mixins)

    @property
    def is_global(self) -> bool:
        return self.scope == "global"

    def kind_spec(self, kind: str | None) -> KindSpec | None:
        if self.kinds is None or kind is None:
            return None
        return self.kinds.get(kind)

    def parent_rules(self, kind: str | None) -> tuple[tuple[str, str | None], ...]:
        ks = self.kind_spec(kind)
        return ks.allowed_parents if ks else self.allowed_parents

    def required_edges(self, kind: str | None) -> tuple[str, ...]:
        ks = self.kind_spec(kind)
        return ks.requires if ks else ()


@dataclass(frozen=True)
class MixinSpec:
    name: str
    slots: dict[str, SlotSpec]
    annotations: dict[str, str]


@dataclass(frozen=True)
class OntologyModel:
    name: str
    version: str
    mixins_version: str | None
    classes: dict[str, ClassSpec]
    mixins: dict[str, MixinSpec]
    global_slots: dict[str, SlotSpec]
    root_class: str
    source_paths: tuple[str, ...] = ()

    def concrete(self) -> list[ClassSpec]:
        return [c for c in self.classes.values() if not c.abstract]

    def cls(self, name: str) -> ClassSpec | None:
        return self.classes.get(name)

    def classes_with_mixin(self, mixin: str) -> list[ClassSpec]:
        return [c for c in self.concrete() if mixin in c.mixins]

    def edge_slots(self) -> dict[str, EdgeSpec]:
        out: dict[str, EdgeSpec] = {}
        for c in self.concrete():
            for name, e in c.edges.items():
                out.setdefault(name, e)
        return out

    def slot_for_rel(self, rel_or_slot: str) -> str | None:
        for name, e in self.edge_slots().items():
            if rel_or_slot in (name, e.rel_type):
                return name
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "mixins_version": self.mixins_version,
            "root_class": self.root_class,
            "classes": {
                c.name: {
                    "kinds": sorted(c.kinds) if c.kinds else [],
                    "mixins": list(c.mixins),
                    "scope": c.scope,
                    "edges": {n: e.rel_type for n, e in c.edges.items()},
                    "fields": {
                        n: {
                            "type": s.base_type,
                            "required": s.required,
                            "owner": s.owner,
                            **({"enum": list(s.enum_values)} if s.enum_values else {}),
                            **({"multivalued": True} if s.multivalued else {}),
                            **({"immutable": s.immutable} if s.immutable else {}),
                        }
                        for n, s in c.slots.items()
                    },
                }
                for c in self.concrete()
            },
            "mixins": {
                m.name: {
                    "fields": {
                        n: {
                            "type": s.base_type,
                            "owner": s.owner,
                            "enum": list(s.enum_values or ()),
                        }
                        for n, s in m.slots.items()
                    },
                    "annotations": m.annotations,
                }
                for m in self.mixins.values()
            },
        }
