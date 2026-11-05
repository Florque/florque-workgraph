from pathlib import Path

import pytest
from florque_graph_core.ontology.loader import OntologyLoadError, load_ontology
from florque_workgraph_domain import ONTOLOGY_PATH


def test_loads_workgraph(model):
    assert model.version == "0.2.0"
    assert model.mixins_version == "0.1.0"
    assert model.root_class == "Project"
    goal = model.classes["Goal"]
    assert goal.labels == ("Goal", "Node", "Expectation")
    assert goal.kinds["key_result"].allowed_parents == (("Goal", "objective"),)
    assert model.classes["WorkItem"].kinds["initiative"].requires == ("serves",)
    assert goal.slots["outcome"].owner == "evaluator"
    assert goal.slots["target_value"].immutable == "active"
    assert model.classes["Actor"].is_global
    assert model.classes["Signal"].edges["about"].targets == {"WorkItem", "Goal", "Project"}


def test_missing_ontology_fails():
    with pytest.raises(OntologyLoadError):
        load_ontology("/nonexistent/schema.yaml")


def test_unknown_annotation_rejected(tmp_path: Path):
    src = ONTOLOGY_PATH.read_text().replace('root: "true"', 'root: "true"\n      colour: blue')
    (tmp_path / "workgraph.linkml.yaml").write_text(src)
    (tmp_path / "mixins.linkml.yaml").write_text(
        (ONTOLOGY_PATH.parent / "mixins.linkml.yaml").read_text()
    )
    with pytest.raises(OntologyLoadError, match="colour"):
        load_ontology(tmp_path / "workgraph.linkml.yaml")


def test_bad_allowed_parent_rejected(tmp_path: Path):
    src = ONTOLOGY_PATH.read_text().replace(
        'allowed_parent: "WorkItem:initiative"}', 'allowed_parent: "WorkItem:saga"}'
    )
    (tmp_path / "workgraph.linkml.yaml").write_text(src)
    (tmp_path / "mixins.linkml.yaml").write_text(
        (ONTOLOGY_PATH.parent / "mixins.linkml.yaml").read_text()
    )
    with pytest.raises(OntologyLoadError, match="saga"):
        load_ontology(tmp_path / "workgraph.linkml.yaml")
