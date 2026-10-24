"""The ontology file must stay valid and must cover the assignment's minimum."""
import copy

from ddn.ontology import REQUIRED_EDGES, REQUIRED_NODES, load_ontology, schema_summary, validate


def test_ontology_is_valid_and_complete():
    o = load_ontology()
    assert validate(o) == []
    assert REQUIRED_NODES <= o.nodes.keys()
    assert REQUIRED_EDGES <= o.edges.keys()


def test_validator_catches_unknown_node_type():
    o = load_ontology()
    broken = copy.deepcopy(o)
    broken.edges["feeds"].to.append("Robott")          # typo in a hand-edited file
    assert any("Robott" in e for e in validate(broken))


def test_relocation_is_representable():
    o = load_ontology()
    assert o.edges["partOf"].time_valid                  # robot moved L1 -> L2 keeps its history
    assert {"passed_at", "inferred"} <= {p.name for p in o.edges["passedThrough"].properties}


def test_schema_summary_for_llm():
    s = schema_summary(load_ontology())
    assert "(Vehicle)-[:passedThrough {passed_at, reader_id, inferred}]->(Station)" in s
