"""Ontology extensions: additive only, parsed from memory, no imports beyond linkml:types."""

from __future__ import annotations

import pytest
from florque_graph_core.ontology.loader import OntologyLoadError, load_ontology
from florque_workgraph_domain import ONTOLOGY_PATH

EXPERIMENTS = """
name: experiments
version: 1.0.0
enums:
  WorkItemKind:
    permissible_values:
      spike:
        description: Time-boxed research.
        annotations:
          allowed_parent: "WorkItem:initiative,WorkItem:epic"
  ExperimentKind:
    permissible_values:
      ab_test:
        annotations:
          allowed_parent: "WorkItem:initiative"
slots:
  hypothesis:
    range: string
classes:
  Experiment:
    is_a: Node
    description: A controlled experiment.
    slots: [hypothesis]
    slot_usage:
      kind:
        range: ExperimentKind
        required: true
"""


def load(*exts: str):
    return load_ontology(ONTOLOGY_PATH, extensions=list(exts))


def test_extension_adds_classes_kinds_and_slots():
    m = load(EXPERIMENTS)
    assert m.version == "0.2.0+experiments@1.0.0"
    assert m.base_version == "0.2.0" and m.extensions == ("experiments@1.0.0",)
    assert "spike" in m.classes["WorkItem"].kinds
    exp = m.classes["Experiment"]
    assert "hypothesis" in exp.slots and set(exp.kinds) == {"ab_test"}
    assert exp.parent_rules("ab_test") == (("WorkItem", "initiative"),)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: x1\nversion: 1.0.0\nimports: [./secrets]\n", "may import only"),
        ("name: x1\nversion: 1.0.0\nimports: ['https://evil.example/s.yaml']\n", "may import only"),
        ("name: x1\nversion: 1.0.0\nclasses:\n  Goal: {is_a: Node}\n", "already exists"),
        ("name: x1\nversion: 1.0.0\nslots:\n  title: {range: integer}\n", "already exists"),
        (
            "name: x1\nversion: 1.0.0\nenums:\n  Outcome:\n    permissible_values: {meh: {}}\n",
            "contract",
        ),
        (
            "name: x1\nversion: 1.0.0\nenums:\n  WorkItemKind:\n    permissible_values: {task: {}}\n",
            "already has",
        ),
        ("name: x1\nversion: 1.0.0\nsubsets: {}\n", "keys not allowed"),
        ("name: X!\nversion: 1.0.0\n", "name must be"),
        ("name: x1\n", "version is required"),
        ("- just\n- a list\n", "mapping"),
        (
            "name: x1\nversion: 1.0.0\nclasses:\n  Orphan: {is_a: Node}\n",
            "allowed_parent",
        ),
        (
            "name: x1\nversion: 1.0.0\nclasses:\n  Weird:\n    is_a: Node\n"
            "    annotations: {allowed_parent: Project, colour: red}\n",
            "Unknown annotation",
        ),
    ],
)
def test_extension_restrictions(text, message):
    with pytest.raises(OntologyLoadError) as e:
        load(text)
    assert message in str(e.value)


def test_extension_size_limit():
    with pytest.raises(OntologyLoadError, match="larger than"):
        load("name: big\nversion: 1.0.0\ndescription: " + "x" * 70_000 + "\n")


def test_extension_names_unique():
    with pytest.raises(OntologyLoadError, match="unique"):
        load(EXPERIMENTS, EXPERIMENTS)
