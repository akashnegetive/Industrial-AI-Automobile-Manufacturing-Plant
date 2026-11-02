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
    llm = FakeLLM([{"can_answer": True, "reason": "", "cypher": "MATCH (v:Vehicle {vin: 'NOPE'}) RETURN v.vin"}],
                  {"dont_know": False, "sentences": [{"text": "made up", "citations": ["NOPE"]}]})
    a = G.ask("Tell me about vehicle NOPE", llm)
    assert a.dont_know and len(llm.prompts) == 1          # the answer step was never called


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
