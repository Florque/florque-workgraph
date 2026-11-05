"""The ontology card: a compact agent-facing summary rendered into the skill."""

from __future__ import annotations

from florque_graph_core.errors import ErrorCode
from florque_graph_core.ontology.model import ClassSpec, OntologyModel


def _parents(allowed: tuple[tuple[str, str | None], ...]) -> str:
    return ", ".join(f"{c}:{k}" if k else c for c, k in allowed) or "—"


def _class_section(c: ClassSpec) -> list[str]:
    lines = [f"### {c.name}", ""]
    if c.description:
        lines += [c.description, ""]
    for key, label in (("use_when", "Use when"), ("not_for", "Not for"), ("branch", "Branch")):
        if key in c.guidance:
            lines.append(f"- **{label}:** {c.guidance[key]}")
    if c.mixins:
        lines.append(f"- **Mixins:** {', '.join(c.mixins)}")
    if c.root:
        lines.append("- **Root:** no parent; one per effort")
    elif c.is_global:
        lines.append("- **Scope:** global (no project_id; joined to projects by member_of)")
    if c.kinds:
        lines += ["", "| Kind | Parent | Requires |", "| --- | --- | --- |"]
        for k in c.kinds.values():
            lines.append(
                f"| {k.name} | {_parents(k.allowed_parents)} | {', '.join(k.requires) or '—'} |"
            )
    elif not c.root and c.allowed_parents:
        lines.append(f"- **Parent:** {_parents(c.allowed_parents)}")
    edges = [e for e in c.edges.values() if e.slot != "part_of"]
    if edges:
        lines += [
            "",
            "Edges: " + "; ".join(f"`{e.slot}` → {', '.join(sorted(e.targets))}" for e in edges),
        ]
    fields = []
    for s in c.slots.values():
        if s.owner == "system" or (s.name == "kind" and not s.enum_name):
            continue
        t = f"{s.enum_name}" if s.enum_name else s.base_type
        flags = []
        if s.required:
            flags.append("required")
        if s.multivalued:
            flags.append("list")
        if s.owner != "human":
            flags.append(f"owner={s.owner}")
        if s.immutable:
            flags.append(f"frozen when {s.immutable}")
        fields.append(f"`{s.name}`: {t}" + (f" ({', '.join(flags)})" if flags else ""))
    lines += ["", "Fields: " + "; ".join(fields)]
    for r in c.rules:
        pre = ", ".join(f"{k}={v.equals_string}" for k, v in r.pre.items() if v.equals_string)
        lines.append(f"- **Rule** (when {pre}): requires {', '.join(r.post)}")
    if c.natural_key:
        lines.append(f"- **Natural key:** {', '.join(c.natural_key)}")
    lines.append("")
    return lines


def render_card(model: OntologyModel) -> str:
    lines = [
        f"# Ontology card: {model.name} {model.version}",
        "",
        f"<!-- ontology_version: {model.version}; mixins_version: {model.mixins_version}. Generated; do not edit. -->",
        "",
        "Every node except the root and global classes has exactly one parent (`parent_id`).",
        "New nodes start as `proposed`. Search before creating; follow error hints.",
        "",
        "## Classes",
        "",
    ]
    for c in model.concrete():
        lines += _class_section(c)
    lines += ["## Enums", ""]
    seen: dict[str, tuple[str, ...]] = {}
    for c in model.concrete():
        for s in c.slots.values():
            if s.enum_name and s.enum_name not in seen and s.name != "kind":
                seen[s.enum_name] = s.enum_values or ()
    for name, values in sorted(seen.items()):
        lines.append(f"- **{name}:** {', '.join(values)}")
    lines += ["", "## Error codes", "", ", ".join(e.value for e in ErrorCode), ""]
    return "\n".join(lines)
