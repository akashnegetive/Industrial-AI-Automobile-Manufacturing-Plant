"""Day 9: GraphRAG safety and grounding. The LLM is replaced by a scripted fake, so no API key is needed."""
import pytest

from ddn import graph
from ddn import graphrag as G

NEO = pytest.mark.skipif(not graph.neo4j_available(wait_s=0), reason="Neo4j not running (docker compose up -d)")


# ---------------------------------------------------------------- validator (no database needed)
@pytest.mark.parametrize("q", [
    "MATCH (n) DETACH DELETE n",
    "MATCH (v:Vehicle) SET v.vin = 'x' RETURN v",
    "CREATE (:Vehicle {vin: 'x'})",
    "MERGE (v:Vehicle {vin: 'x'}) RETURN v",
    "CALL db.labels()",
    "LOAD CSV FROM 'file:///x' AS r RETURN r",
    "MATCH (v:Vehicle) RETURN v; MATCH (n) DELETE n",
    "match (v:Vehicle) remove v.vin return v",                  # lower case does not get through
])
def test_writes_and_procedures_are_rejected(q):
    with pytest.raises(G.CypherRejected):
        G.validate(q)


def test_unknown_label_relationship_and_property_are_rejected():
    for q in ["MATCH (s:ShiftSupervisor) RETURN s", "MATCH (v:Vehicle)-[:supervisedBy]->(x) RETURN x",
              "MATCH (v:Vehicle) RETURN v.film_thickness"]:
        with pytest.raises(G.CypherRejected):
            G.validate(q)


def test_property_and_alias_names_that_look_like_keywords_are_fine():
    q = G.validate("MATCH (v:Vehicle)-[p:processedBy]->(e:Asset) RETURN e.fl AS fl, p.start AS start ORDER BY start")
    assert q.endswith("LIMIT 100")


def test_keywords_inside_strings_are_ignored():
    G.validate("MATCH (w:WorkOrder) WHERE w.short_text CONTAINS 'DELETE; SET' RETURN w.wo_number")


# ---------------------------------------------------------------- grounding (no database needed)
def test_sentences_without_valid_citations_are_dropped():
    rows = [{"wo_number": "4102961", "fl": "DDN1-BIW-L2-ST04-RB07"}]
    kept, dropped = G.ground([
        {"text": "RB07 caused it.", "citations": ["DDN1-BIW-L2-ST04-RB07"]},
        {"text": "The supervisor was Ravi.", "citations": []},              # no citation, no claim
        {"text": "WO 4109999 fixed it.", "citations": ["4109999"]},           # invented ID
        {"text": "Mixed.", "citations": ["4102961", "4109999"]},              # one bad citation is enough
    ], rows)
    assert [s["text"] for s in kept] == ["RB07 caused it."] and dropped == 3


@pytest.mark.parametrize("q", [
    "MATCH (d:Defect)<-[:causedBy]-(e:Equipment) RETURN e.fl",                    # arrow the wrong way
    "MATCH (a:AnomalyEvent)-[:hasTimeSeries]->(t:TimeSeries) RETURN t.tag",        # wrong start label
    "MATCH (v:Vehicle) MATCH (l:SupplierLot)<-[:containsPart]-(v) RETURN v.vin",   # label known from earlier
])
def test_relationships_must_follow_the_ontology_direction(q):
    with pytest.raises(G.CypherRejected, match="direction"):
        G.validate(q)


def test_right_directions_and_asset_label_pass():
    G.validate("MATCH (d:Defect)-[:causedBy]->(e:AnomalyEvent)<-[:hasEvent]-(eq:Asset) RETURN eq.fl, e.anomaly_id")
    G.validate("MATCH (a:Asset)-[:partOf*0..4]->(:Asset {fl: 'X'}) MATCH (a)-[:hasTimeSeries]->(t:TimeSeries) RETURN t.tag")


def test_counts_and_matched_filter_values_can_be_cited():
    rows = [{"vehicle_count": 1785}]
    cypher = "MATCH (l:SupplierLot {lot_id: 'WS-260904-B'})<-[:fromLot]-(:Part)<-[:containsPart]-(v) RETURN count(v)"
    kept, _ = G.ground([{"text": "1,785 vehicles got lot WS-260904-B.", "citations": ["1,785", "WS-260904-B"]}],
                       rows, cypher)
    assert len(kept) == 1
    assert G.ground([{"text": "x", "citations": ["WS-260904-B"]}], [], cypher)[0] == []   # no rows, no citing


@NEO
def test_prompt_examples_are_valid_and_return_data():
    with graph.driver() as d, d.session() as s:
        for block in [b.split("\n", 1)[1] for b in G.EXAMPLES.split("\n\n") if "\nMATCH" in b]:
            assert G.run_read(s, G.validate(block, s)), block


def test_last_tuesday_is_8_september():
    assert G.parse_day("last Tuesday").isoformat() == "2026-09-08"
    assert G.parse_day("on 10 September").isoformat() == "2026-09-10"


# ---------------------------------------------------------------- full loop with a fake LLM
class FakeLLM:
    name = "fake"

    def __init__(self, plans, answer):
        self.plans, self.answer, self.prompts = list(plans), answer, []

    def json(self, system, user, schema, schema_name):
        self.prompts.append(user)
        return self.plans.pop(0) if schema_name == "cypher_plan" else self.answer


@NEO
def test_bad_query_is_retried_with_the_error_then_answered_with_citations():
    llm = FakeLLM(
        plans=[{"can_answer": True, "reason": "", "cypher": "MATCH (w:WorkOrder) DETACH DELETE w"},
               {"can_answer": True, "reason": "", "cypher":
                "MATCH (e:AnomalyEvent {anomaly_id: 'AN-003'})<-[:hasEvent]-(a:Asset) "
                "RETURN e.anomaly_id AS anomaly_id, a.fl AS fl, e.confirming_wo AS wo"}],
        answer={"dont_know": False, "sentences": [
            {"text": "AN-003 is on robot RB07.", "citations": ["AN-003", "DDN1-BIW-L2-ST04-RB07"]},
            {"text": "It was caused by a bad batch of tips.", "citations": ["batch-42"]}]})
    a = G.ask("Which robot caused the cold welds?", llm)
    assert a.attempts == 2 and "rejected" in llm.prompts[1]
    assert not a.dont_know and len(a.sentences) == 1 and a.dropped_sentences == 1
    assert "DDN1-BIW-L2-ST04-RB07" in a.text()


@NEO
def test_model_says_cannot_answer_gives_i_dont_know():
    llm = FakeLLM([{"can_answer": False, "reason": "No supervisor data in the graph.", "cypher": ""}], None)
    a = G.ask("Who was the shift supervisor on 9 September?", llm)
    assert a.dont_know and a.sentences == [] and "supervisor" in a.reason


@NEO
def test_empty_result_gives_i_dont_know_without_asking_the_llm_to_guess():
    empty = {"can_answer": True, "reason": "", "cypher": "MATCH (v:Vehicle {vin: 'NOPE'}) RETURN v.vin"}
    llm = FakeLLM([empty] * G.MAX_ATTEMPTS, {"dont_know": False, "sentences": [{"text": "made up", "citations": ["NOPE"]}]})
    a = G.ask("Tell me about vehicle NOPE", llm)
    assert a.dont_know and len(llm.prompts) == G.MAX_ATTEMPTS        # retried, but the answer step never ran
    assert "0 rows" in llm.prompts[1]


@NEO
def test_offline_baseline_answers_all_ten_evaluation_questions():
    results = G.evaluate(provider=None)
    assert all(ok for *_, ok in results), [q for q, *_, ok in results if not ok]


@NEO
def test_ask_screen_renders_an_answer(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("DDN_LLM", "offline")
    at = AppTest.from_file("../apps/ask_app.py", default_timeout=60).run()
    at.text_input[0].input("How many vehicles received parts from supplier lot WS-260904-B?").run()
    assert not at.exception and any("1785" in m.value for m in at.markdown)


def test_one_variable_for_two_node_types_is_rejected():
    with pytest.raises(G.CypherRejected, match="two different node types"):
        G.validate("MATCH (v:Vehicle)-[:passedThrough]->(l:Line) "
                   "OPTIONAL MATCH (v)-[:containsPart]->(:Part)-[:fromLot]->(l:SupplierLot) RETURN l.lot_id")
    G.validate("MATCH (a:Asset:Equipment)-[:hasEvent]->(e:AnomalyEvent) MATCH (a:Asset) RETURN a.fl")


def test_an_id_inside_a_text_value_can_be_cited_but_not_a_fragment():
    rows = [{"anomaly_id": "AN-006", "reason": "Crater (PD-020) on exposed cars; WO 4102963: AHU TC2 valve stuck"}]
    kept, dropped = G.ground([{"text": "WO 4102963 fixed it.", "citations": ["AN-006", "4102963"]},
                              {"text": "part of a number", "citations": ["4102"]}], rows)
    assert len(kept) == 1 and dropped == 1


def test_supplier_lot_cause_is_only_the_door_seal_lot():
    lc = graph.supplier_lot_causes()
    assert set(lc.lot_id) == {"WS-260904-B"} and len(lc) == 85


@NEO
def test_expand_adds_asset_and_work_order_of_an_anomaly_and_the_lot_cause():
    with graph.driver() as d, d.session() as s:
        ctx = G.expand(s, [{"anomaly_id": "AN-006"}, {"lot_id": "WS-260904-B"}, {"lot_id": "BT-260904-A"}])
    assert {"fl": "DDN1-PNT-AHU-AHUTC2", "wo_number": "4102963"}.items() <= next(
        c for c in ctx if c["context"] == "anomaly").items()
    assert [c["lot_id"] for c in ctx if c["context"] == "supplier lot root cause"] == ["WS-260904-B"]


def test_no_evaluation_answer_is_written_into_the_prompt_examples():
    answers = {e for _, exp, _ in G.EVAL + G.HOLDOUT + G.HOLDOUT_2 for e in exp}
    leaked = {a for a in answers if a in G.EXAMPLES}
    assert not leaked, leaked



@NEO
def test_retry_message_names_hops_that_have_no_data():
    with graph.driver() as d, d.session() as s:
        msg = G.empty_hops("MATCH (d:Defect {defect_code: 'AU-077'})-[:causedBy]->(eq:Asset) RETURN eq.fl", s)
    assert msg and "AnomalyEvent" in msg[0] and "has no edges" in msg[0]


@NEO
def test_expand_finds_the_anomaly_of_an_asset_in_the_rows():
    with graph.driver() as d, d.session() as s:
        ctx = G.expand(s, [{"fl": "DDN1-PNT-AHU-AHUTC1-SF", "wo_number": "4102547"}])
    assert any(c.get("anomaly_id") == "AN-005" and c.get("wo_number") == "4102967" for c in ctx)


def test_scorer_accepts_sensor_fault_for_sensor_fault_enum():
    a = G.Answer("q", "x", sentences=[{"text": "AN-007 was a sensor fault.", "citations": ["AN-007"]}])
    assert G.score(a, ["AN-007", "sensor_fault"], False)
