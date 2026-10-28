"""Day 7: review queue/decisions, graph loader rules, and (if Neo4j is running) the loaded graph."""
import pandas as pd
import pytest

from ddn import graph, review
from ddn.tags import stage_assets


@pytest.fixture
def temp_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "DECISIONS", tmp_path / "decisions.csv")
    monkeypatch.setattr(review, "REVIEW_DIR", tmp_path)
    return tmp_path / "decisions.csv"


def test_review_queue_has_the_middle_band():
    q = review.build_queue()
    assert set(q.kind) == {"tag", "workorder", "document"}
    assert q.confidence.between(0, 1).all()


def test_decision_becomes_training_label_and_engineer_edge(temp_decisions):
    item = {"item_id": "wo:4102964", "kind": "workorder", "record": "4102964",
            "proposed_fl": "DDN1-ASM-FN1-ST03-NR14"}
    review.save_decision(item, "approve", item["proposed_fl"], "tester")
    assert review.engineer_labels("workorder") == {"4102964": "DDN1-ASM-FN1-ST03-NR14"}
    links = graph.approved_links("workorder", "wo_number", "wo_matches_rules.parquet")
    row = links[links.wo_number == "4102964"].iloc[0]
    assert row.method == "engineer" and row.confidence == 1.0


def test_later_decision_overrides_earlier(temp_decisions):
    item = {"item_id": "tag:X", "kind": "tag", "record": "X", "proposed_fl": "A"}
    review.save_decision(item, "approve", "A", "t")
    review.save_decision(item, "correct", "B", "t")
    assert review.engineer_labels("tag") == {"X": "B"}


def test_edges_refuse_missing_provenance():
    df = pd.DataFrame({"a": ["x"], "b": ["y"], "source_system": ["MES"], "method": ["rule"], "confidence": [0.9]})
    with pytest.raises(ValueError, match="provenance"):
        graph.edges(None, "feeds", df, ("Asset", "fl", "a"), ("Asset", "fl", "b"))


def test_asset_labels():
    assets = stage_assets()
    stations = pd.read_parquet(graph.STAGING / "stations.parquet")
    lab = graph.asset_nodes(assets, stations, {}).set_index("fl").label
    assert lab["DDN1-BIW-L2-ST04-RB07"] == "Equipment"
    assert lab["DDN1-BIW-L2-ST04-RB07-WG"] == "Component"
    assert lab["DDN1-BIW-L2-ST04"] == "Station"
    assert lab["DDN1-PRS-DIES"] == "Line"                      # Area-level FL loads as Line (ontology 1.1.0)


neo4j = pytest.mark.skipif(not graph.neo4j_available(wait_s=0), reason="Neo4j not running (docker compose up -d)")


@neo4j
def test_graph_has_full_provenance_and_respects_ontology():
    v = graph.validate_graph()
    assert v["missing_provenance"] == 0 and v["ontology_violations"] == {} and v["enum_violations"] == {}


@neo4j
def test_relocated_robot_has_time_bounded_partof():
    with graph.driver() as d, d.session() as s:
        rows = [dict(r) for r in s.run(
            "MATCH (:Asset {fl: 'DDN1-BIW-L2-ST06-RB12'})-[r:partOf]->(p) "
            "RETURN p.fl AS parent, r.valid_from IS NOT NULL AS has_from, r.valid_to IS NOT NULL AS has_to")]
    assert {"parent": "DDN1-BIW-L2-ST06", "has_from": True, "has_to": False} in rows
    assert {"parent": "DDN1-BIW-L1-ST03", "has_from": False, "has_to": True} in rows


@neo4j
def test_recall_scope_query():
    from ddn.queries import run
    with graph.driver() as d, d.session() as s:
        d5 = run(s, "D5")
    assert d5.vehicles.sum() == 1785 and d5.with_door_leak.sum() == 85
