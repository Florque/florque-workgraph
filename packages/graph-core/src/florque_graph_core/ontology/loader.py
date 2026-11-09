"""Load a LinkML schema (plus fragments) with SchemaView and compile it to an OntologyModel."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from linkml_runtime.linkml_model.meta import SchemaDefinition
from linkml_runtime.loaders import yaml_loader
from linkml_runtime.utils.schemaview import SchemaView

from florque_graph_core.ontology import annotations as vocab
from florque_graph_core.ontology.model import (
    ClassSpec,
    Condition,
    EdgeSpec,
    KindSpec,
    MixinSpec,
    OntologyModel,
    RuleSpec,
    SlotSpec,
)


class OntologyLoadError(ValueError):
    """Raised when the ontology is missing, malformed or uses unknown annotations."""


_TYPE_MAP = {
    "str": "str",
    "int": "int",
    "float": "float",
    "Decimal": "float",
    "double": "float",
    "Bool": "bool",
    "bool": "bool",
    "XSDDate": "date",
    "XSDDateTime": "datetime",
}


def ann(element: Any) -> dict[str, str]:
    """Annotations of any LinkML element as a plain dict (handles dict and JsonObj forms)."""
    a = getattr(element, "annotations", None)
    if not a:
        return {}
    items: Iterable[tuple[str, Any]] = a.items() if isinstance(a, dict) else a._items()
    out: dict[str, str] = {}
    for k, v in items:
        if hasattr(v, "value"):
            v = v.value
        elif isinstance(v, dict):
            v = v.get("value")
        out[str(k)] = "" if v is None else str(v)
    return out


def _check_keys(where: str, found: dict[str, str], allowed: set[str]) -> None:
    unknown = set(found) - allowed
    if unknown:
        raise OntologyLoadError(
            f"Unknown annotation(s) {sorted(unknown)} on {where}. Allowed: {sorted(allowed)}"
        )


def _parse_parents(value: str) -> tuple[tuple[str, str | None], ...]:
    out: list[tuple[str, str | None]] = []
    for part in (p.strip() for p in value.split(",") if p.strip()):
        cls, _, kind = part.partition(":")
        out.append((cls, kind or None))
    return tuple(out)


def _csv(value: str | None) -> tuple[str, ...]:
    return tuple(p.strip() for p in (value or "").split(",") if p.strip())


class _Compiler:
    def __init__(self, sv: SchemaView) -> None:
        self.sv = sv

    def base_type(self, rng: str | None) -> tuple[str, tuple[str, ...] | None, str | None]:
        sv = self.sv
        if rng is None:
            return "str", None, None
        enum = sv.get_enum(rng)
        if enum is not None:
            return "enum", tuple(str(k) for k in enum.permissible_values), rng
        t = sv.get_type(rng)
        if t is not None:
            seen = set()
            while t is not None and t.name not in seen:
                seen.add(t.name)
                if t.base:
                    return _TYPE_MAP.get(t.base, "str"), None, None
                t = sv.get_type(t.typeof) if t.typeof else None
        return "str", None, None

    def slot_spec(self, name: str, induced: Any) -> SlotSpec:
        a = ann(induced)
        _check_keys(f"slot {name}", a, vocab.SLOT_ANNOTATIONS)
        owner = a.get("owner", "human")
        if owner not in vocab.OWNERS:
            raise OntologyLoadError(f"slot {name}: owner must be one of {sorted(vocab.OWNERS)}")
        if induced.identifier:
            owner = "system"
        base, values, enum_name = self.base_type(induced.range)
        return SlotSpec(
            name=name,
            base_type=base,
            enum_values=values,
            enum_name=enum_name,
            required=bool(induced.required) and not induced.identifier,
            multivalued=bool(induced.multivalued),
            owner=owner,
            immutable=a.get("immutable") or None,
            description=induced.description or "",
        )

    def edge_targets(self, induced: Any) -> frozenset[str]:
        sv = self.sv
        ranges = [x.range for x in (induced.any_of or []) if x.range] or [induced.range]
        out: set[str] = set()
        for r in ranges:
            if r is None or sv.get_class(r) is None:
                raise OntologyLoadError(f"edge slot {induced.name}: range {r!r} is not a class")
            for d in sv.class_descendants(r, reflexive=True):
                c = sv.get_class(d)
                if c is not None and not c.abstract and not c.mixin:
                    out.add(d)
        return frozenset(out)

    def rules(self, cls_name: str) -> tuple[RuleSpec, ...]:
        out: list[RuleSpec] = []
        for anc in self.sv.class_ancestors(cls_name):
            c = self.sv.get_class(anc)
            for r in c.rules or []:
                out.append(
                    RuleSpec(
                        description=r.description or "",
                        pre=self._conds(r.preconditions),
                        post=self._conds(r.postconditions),
                    )
                )
        return tuple(out)

    @staticmethod
    def _conds(expr: Any) -> dict[str, Condition]:
        if expr is None or not expr.slot_conditions:
            return {}
        out: dict[str, Condition] = {}
        for name, sc in expr.slot_conditions.items():
            out[str(name)] = Condition(
                equals_string=sc.equals_string,
                equals_number=sc.equals_number,
                required=bool(sc.required),
            )
        return out


# ---------------------------------------------------------------- extensions

EXTENSION_KEYS = {
    "id",
    "name",
    "title",
    "description",
    "version",
    "prefixes",
    "default_prefix",
    "default_range",
    "imports",
    "enums",
    "slots",
    "classes",
}
EXTENSION_IMPORTS = {"linkml:types"}
MAX_EXTENSION_BYTES = 64 * 1024
_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
_VERSION = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,30}$")


@dataclass(frozen=True)
class Extension:
    """A parsed, structurally checked extension (user-supplied YAML)."""

    name: str
    version: str
    data: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.name}@{self.version}"


def parse_extension(text: str) -> Extension:
    """Parse extension YAML without touching the filesystem or network.

    Extensions are additive: new classes, slots and enums, plus new values on enums of the
    base schema. They cannot change or remove anything the base defines, and may import only
    ``linkml:types``.
    """
    if len(text.encode()) > MAX_EXTENSION_BYTES:
        raise OntologyLoadError(f"extension is larger than {MAX_EXTENSION_BYTES // 1024} KiB")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise OntologyLoadError(f"extension is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise OntologyLoadError("extension must be a YAML mapping")
    unknown = set(data) - EXTENSION_KEYS
    if unknown:
        raise OntologyLoadError(
            f"extension keys not allowed: {sorted(unknown)}; allowed: {sorted(EXTENSION_KEYS)}"
        )
    name, version = str(data.get("name", "")), str(data.get("version", ""))
    if not _NAME.match(name):
        raise OntologyLoadError("extension name must be lowercase letters, digits, - or _")
    if not _VERSION.match(version):
        raise OntologyLoadError("extension version is required, e.g. 1.0.0")
    imports = data.get("imports") or []
    if not isinstance(imports, list) or set(map(str, imports)) - EXTENSION_IMPORTS:
        raise OntologyLoadError(f"extensions may import only {sorted(EXTENSION_IMPORTS)}")
    for key in ("enums", "slots", "classes"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise OntologyLoadError(f"extension {key} must be a mapping")
    return Extension(name, version, data)


def _apply_extension(sv: SchemaView, ext: Extension) -> None:
    data = ext.data
    base_classes, base_slots = set(sv.all_classes()), set(sv.all_slots())
    own_enums = sv.schema.enums  # enums of the base schema itself (not imported contracts)
    for c in data.get("classes") or {}:
        if c in base_classes:
            raise OntologyLoadError(f"extension {ext.name}: class {c} already exists")
    for sl in data.get("slots") or {}:
        if sl in base_slots:
            raise OntologyLoadError(f"extension {ext.name}: slot {sl} already exists")
    extended: list[str] = []
    for e, body in (data.get("enums") or {}).items():
        if e in sv.all_enums():
            if e not in own_enums:
                raise OntologyLoadError(
                    f"extension {ext.name}: enum {e} belongs to a contract and cannot be extended"
                )
            new_values = set((body or {}).get("permissible_values") or {})
            if set((body or {}).keys()) - {"permissible_values"}:
                raise OntologyLoadError(
                    f"extension {ext.name}: an existing enum ({e}) only takes permissible_values"
                )
            clash = new_values & set(own_enums[e].permissible_values)
            if clash:
                raise OntologyLoadError(f"extension {ext.name}: {e} already has {sorted(clash)}")
            extended.append(e)
    doc = {
        "id": data.get("id") or f"https://florque.com/ontology/ext/{ext.name}",
        "name": ext.name,
        "version": ext.version,
        "prefixes": data.get("prefixes") or {"florque": "https://florque.com/ontology/"},
        "default_prefix": data.get("default_prefix") or "florque",
        "default_range": data.get("default_range") or "string",
        "enums": data.get("enums") or {},
        "slots": data.get("slots") or {},
        "classes": data.get("classes") or {},
    }
    try:
        frag = yaml_loader.loads(yaml.safe_dump(doc), target_class=SchemaDefinition)
    except Exception as e:  # noqa: BLE001 - surface LinkML's message to the author
        raise OntologyLoadError(f"extension {ext.name}: {e}") from e
    for enum_name in extended:
        for k, pv in frag.enums[enum_name].permissible_values.items():
            own_enums[enum_name].permissible_values[k] = pv
        del frag.enums[enum_name]
    sv.merge_schema(frag)


def load_ontology(
    path: str | Path,
    fragments: Sequence[str | Path] = (),
    extensions: Sequence[str | Extension] = (),
) -> OntologyModel:
    """Load the base schema, trusted fragment files and user extensions (YAML text)."""
    path = Path(path)
    if not path.is_file():
        raise OntologyLoadError(f"Ontology not found: {path}")
    sv = SchemaView(str(path))
    for frag in fragments:
        sv.merge_schema(SchemaView(str(frag)).schema)
    exts = [e if isinstance(e, Extension) else parse_extension(e) for e in extensions]
    names = [e.name for e in exts]
    if len(set(names)) != len(names):
        raise OntologyLoadError(f"extension names must be unique, got {names}")
    sv.imports_closure()  # resolve the trusted imports before user content is merged
    for ext in exts:
        _apply_extension(sv, ext)
    sv.set_modified()
    sv.imports_closure()  # populates schema_map
    comp = _Compiler(sv)

    mixins_version: str | None = None
    for name, schema in sv.schema_map.items():
        if name.startswith("linkml:"):
            continue
        a = ann(schema)
        _check_keys(f"schema {name}", a, vocab.SCHEMA_ANNOTATIONS)
        mixins_version = a.get("mixins_version", mixins_version)

    for ename in sv.all_enums():
        for vname, pv in sv.get_enum(ename).permissible_values.items():
            _check_keys(f"enum value {ename}.{vname}", ann(pv), vocab.ENUM_VALUE_ANNOTATIONS)

    global_slots: dict[str, SlotSpec] = {}
    for sname in sv.all_slots():
        s = sv.get_slot(sname)
        a = ann(s)
        _check_keys(f"slot {sname}", a, vocab.SLOT_ANNOTATIONS)
        if "edge" not in a:
            global_slots[sname] = comp.slot_spec(sname, s)

    mixins: dict[str, MixinSpec] = {}
    classes: dict[str, ClassSpec] = {}
    for cname in sv.all_classes():
        c = sv.get_class(cname)
        a = ann(c)
        _check_keys(f"class {cname}", a, vocab.CLASS_ANNOTATIONS)
        slots: dict[str, SlotSpec] = {}
        edges: dict[str, EdgeSpec] = {}
        for sname in sv.class_slots(cname):
            induced = sv.induced_slot(sname, cname)
            sa = ann(induced)
            _check_keys(f"slot {cname}.{sname}", sa, vocab.SLOT_ANNOTATIONS)
            if "edge" in sa:
                edges[sname] = EdgeSpec(
                    slot=sname,
                    rel_type=sa["edge"],
                    targets=comp.edge_targets(induced),
                    multivalued=bool(induced.multivalued),
                    properties=_csv(sa.get("edge_properties")),
                    description=induced.description or "",
                )
            else:
                slots[sname] = comp.slot_spec(sname, induced)
        if c.mixin:
            mixins[cname] = MixinSpec(name=cname, slots=slots, annotations=a)
            continue

        kinds: dict[str, KindSpec] | None = None
        kind_required = False
        if "kind" in slots and slots["kind"].enum_name:
            kind_required = slots["kind"].required
            enum = sv.get_enum(slots["kind"].enum_name)
            kinds = {}
            for vname, pv in enum.permissible_values.items():
                pa = ann(pv)
                kinds[str(vname)] = KindSpec(
                    name=str(vname),
                    allowed_parents=_parse_parents(pa.get("allowed_parent", "")),
                    requires=_csv(pa.get("requires")),
                    description=pv.description or "",
                )

        dedupe_scope = a.get("dedupe_scope", "parent")
        if dedupe_scope not in vocab.DEDUPE_SCOPES:
            raise OntologyLoadError(f"class {cname}: dedupe_scope {dedupe_scope!r} invalid")
        merge = a.get("merge", "additive")
        if merge not in vocab.MERGE_MODES:
            raise OntologyLoadError(f"class {cname}: merge {merge!r} invalid")
        all_mixins: list[str] = []
        for anc in sv.class_ancestors(cname):
            ac = sv.get_class(anc)
            if ac.mixin and anc not in all_mixins and anc != cname:
                all_mixins.append(anc)
        classes[cname] = ClassSpec(
            name=cname,
            abstract=bool(c.abstract),
            ancestors=tuple(x for x in sv.class_ancestors(cname) if x != cname),
            mixins=tuple(all_mixins),
            slots=slots,
            edges=edges,
            kinds=kinds,
            kind_required=kind_required,
            allowed_parents=_parse_parents(a.get("allowed_parent", "")),
            rules=comp.rules(cname),
            root=a.get("root", "").lower() == "true",
            scope=a.get("scope", "project"),
            natural_key=_csv(a.get("natural_key")),
            dedupe_scope=dedupe_scope,
            merge=merge,
            guidance={k: a[k] for k in ("branch", "use_when", "not_for") if k in a},
            description=c.description or "",
        )

    roots = [c.name for c in classes.values() if c.root]
    if len(roots) != 1:
        raise OntologyLoadError(f"Exactly one class must be annotated root: true, found {roots}")
    base_version = str(sv.schema.version or "0.0.0")
    model = OntologyModel(
        name=sv.schema.name,
        version="+".join([base_version, *(e.label for e in exts)]),
        base_version=base_version,
        extensions=tuple(e.label for e in exts),
        mixins_version=mixins_version,
        classes=classes,
        mixins=mixins,
        global_slots=global_slots,
        root_class=roots[0],
        source_paths=(str(path), *(str(f) for f in fragments)),
    )
    _check_references(model)
    return model


def _check_references(model: OntologyModel) -> None:
    for c in model.concrete():
        if not (c.root or c.is_global):
            placeable = [k.name for k in (c.kinds or {}).values() if not k.allowed_parents]
            if c.kinds is None and not c.allowed_parents:
                raise OntologyLoadError(f"{c.name} needs an allowed_parent annotation")
            if c.kinds is not None and placeable:
                raise OntologyLoadError(
                    f"{c.name} kinds {placeable} need an allowed_parent annotation"
                )
        rules = list(c.allowed_parents)
        for k in (c.kinds or {}).values():
            rules.extend(k.allowed_parents)
            for req in k.requires:
                if req not in c.edges:
                    raise OntologyLoadError(f"{c.name}:{k.name} requires unknown edge {req!r}")
        for pcls, pkind in rules:
            pc = model.classes.get(pcls)
            if pc is None:
                raise OntologyLoadError(f"{c.name}: allowed_parent class {pcls!r} unknown")
            if pkind and (pc.kinds is None or pkind not in pc.kinds):
                raise OntologyLoadError(f"{c.name}: allowed_parent kind {pcls}:{pkind} unknown")
        for f in c.natural_key:
            if f not in c.slots:
                raise OntologyLoadError(f"{c.name}: natural_key field {f!r} is not a slot")
