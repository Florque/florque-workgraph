from florque_workgraph_domain import GENERATED_DIR
from florque_workgraph_domain.generate import artifacts


def test_generated_artifacts_are_current():
    for name, content in artifacts().items():
        assert (GENERATED_DIR / name).read_text() == content, f"{name} drifted; run fwg-gen"


def test_constraints_cover_dedupe_and_ids():
    text = artifacts()["constraints.cypher"]
    assert "REQUIRE n.id IS UNIQUE" in text
    assert "FOR (n:WorkItem) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE" in text
