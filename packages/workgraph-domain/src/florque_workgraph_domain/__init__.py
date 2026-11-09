"""florque-workgraph-domain: the work-graph domain as data (LinkML ontology) plus a few functions."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from florque_graph_core import GraphCore, OntologyModel, load_ontology
from florque_graph_core.hooks import Hook
from florque_graph_core.store.base import GraphStore

from florque_workgraph_domain.policies import WorkgraphPolicy

PACKAGE_DIR = Path(__file__).parent
ONTOLOGY_PATH = PACKAGE_DIR / "ontology" / "workgraph.linkml.yaml"
MIXINS_PATH = PACKAGE_DIR / "ontology" / "mixins.linkml.yaml"
GENERATED_DIR = PACKAGE_DIR / "generated"
MODULES = {"impact": PACKAGE_DIR / "ontology" / "modules" / "impact.fragment.yaml"}


def load(modules: Sequence[str] = (), extensions: Sequence[str] = ()) -> OntologyModel:
    """The workgraph ontology, optional bundled modules and user extensions (YAML text)."""
    return load_ontology(ONTOLOGY_PATH, [MODULES[m] for m in modules], extensions)


def build_core(
    store: GraphStore,
    hooks: Sequence[Hook] = (),
    modules: Sequence[str] = (),
    extensions: Sequence[str] = (),
    **kwargs: object,
) -> GraphCore:
    """GraphCore wired with the workgraph ontology (plus extensions) and policy."""
    return GraphCore(load(modules, extensions), store, WorkgraphPolicy(), hooks, **kwargs)  # type: ignore[arg-type]


__all__ = ["GENERATED_DIR", "MIXINS_PATH", "ONTOLOGY_PATH", "WorkgraphPolicy", "build_core", "load"]
