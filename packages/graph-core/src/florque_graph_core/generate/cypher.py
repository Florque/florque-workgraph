from __future__ import annotations

from florque_graph_core.integrity import build_checks
from florque_graph_core.ontology.model import OntologyModel
from florque_graph_core.store import queries as q


def _header(model: OntologyModel, what: str) -> str:
    return f"// {what} for ontology {model.name} {model.version} (mixins {model.mixins_version}).\n// Generated; do not edit.\n"


def render_constraints(model: OntologyModel) -> str:
    return _header(model, "Constraints and indexes") + "".join(
        f"{s};\n" for s in q.constraint_statements(model)
    )


def render_integrity(model: OntologyModel) -> str:
    out = [_header(model, "Integrity checks (parameter $project_id); each returns violation rows")]
    for chk in build_checks(model):
        out.append(f"\n// {chk.name}: {chk.description}\n{q.integrity_query(chk)};\n")
    return "".join(out)
