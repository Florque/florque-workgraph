from florque_workgraph_domain import GENERATED_DIR
from florque_workgraph_domain.generate import _plugin_skill, artifacts


def test_generated_artifacts_are_current():
    for path, content in artifacts().items():
        assert path.read_text() == content, f"{path.name} drifted; run fwg-gen"


def test_constraints_cover_dedupe_and_ids():
    text = artifacts()[GENERATED_DIR / "constraints.cypher"]
    assert "REQUIRE n.id IS UNIQUE" in text
    assert "FOR (n:WorkItem) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE" in text


def test_plugin_skill_embeds_the_card():
    skill = _plugin_skill()
    assert skill is not None, "plugin/.claude-plugin/plugin.json not found"
    text = artifacts()[skill]
    assert text.startswith("---\nname: workgraph\n")
    assert "## Ontology card (base schema)" in text and "### WorkItem" in text
