# Day 9 – Part E2: GraphRAG (questions in plain English, answers from the graph)

## What it does

An engineer types *"Why did water-leak defects rise on Line 2 last Tuesday?"* and gets:

> 15 WL-104 leaks at the Front door LH upper on 08 Sep were on cars with door-seal lot WS-260904-B. [WS-260904-B, D700249, …]

Every sentence carries citations: IDs that really appear in the query result. The Cypher query and the rows
are shown too, so anyone can check the answer.

```
question ──LLM──> {can_answer, reason, cypher}
                     │ can_answer=false ───────────────────────────────> "I don't know" + reason
                     ▼
               validate()  ── rejected ──> retry once, with the error message given to the LLM
                     ▼
         run in a READ transaction, 10 s timeout, LIMIT 100
                     │ 0 rows ─────────────────────────────────────────> "I don't know"
                     ▼
     LLM writes {dont_know, sentences:[{text, citations}]} from the rows only
                     ▼
     ground(): drop every sentence whose citations are not in the rows
                     │ nothing left ───────────────────────────────────> "I don't know"
                     ▼
                cited answer
```

## Why GraphRAG and not "put the documents in a vector store"

The questions are about **relationships and counts**: which cars passed which robot, which lot those cars
got, how many defects. A vector search finds similar text; it can't count 1,785 vehicles or follow
vehicle → part → lot → defect. The graph already holds those links (with provenance), so the LLM only has to
translate the question into a query. The facts come from the database, not from the model's memory.

## The safety rules are in code, not only in the prompt

A prompt that says "don't write data" can be ignored by the model. So `validate()` checks every query:

| Check | Stops |
|---|---|
| Forbidden keywords (`CREATE MERGE DELETE SET REMOVE DROP LOAD CALL FOREACH …`), any case, outside strings | Writes, procedures, file access |
| Only one statement (`;`) | `MATCH … ; MATCH (n) DELETE n` |
| Every label and relationship type must be in the ontology | Hallucinated schema (`:ShiftSupervisor`) |
| Every property must be in the ontology | Hallucinated fields (`v.film_thickness`) |
| `EXPLAIN` on Neo4j | Syntax errors, before anything runs |
| `LIMIT 100` added if missing | Huge results |
| Run with `execute_read` + timeout | Defence in depth: Neo4j itself refuses writes in a read transaction; a slow query is stopped |

Property names, aliases and map keys that look like keywords (`p.start AS start`) are allowed. That was a real
bug found while building: the first version rejected `ORDER BY start`.

Rejected queries get **one retry**, with the error message sent back to the LLM ("unknown property
film_thickness"). That fixes most small mistakes without loops.

## "No citation, no claim" and "I don't know"

`ground()` keeps a sentence only if it cites at least one value **and every** cited value appears somewhere in
the result rows. An invented work order number, or a sentence citing nothing, is removed and counted
(`dropped_sentences` in the report). There are three ways to get "I don't know", and none needs the model to
admit it: the model says the schema can't answer, the query returns 0 rows, or no sentence survives grounding.

Two of the ten test questions must give "I don't know": paint film thickness (not in the data) and the
shift supervisor (not in the data). Answering those with a guess counts as a failure.

## What the LLM is given (`cypher_prompt`)

- Today's date (**Tue 15 Sep 2026**: the data ends on 14 Sep) so "last Tuesday" means 8 Sep.
- The schema from `ontology.schema_summary()`: the same ontology the loader enforces. That is why Day 9 started
  by bumping the ontology to **v1.3.0**: the graph had properties the YAML didn't declare, and the validator
  would have rejected correct queries. Now the live graph has 0 undeclared properties.
- Real values read from the graph: defect codes, defect families, anomaly verdicts, work-order types,
  line FLs. Without these the model guesses `defect_type = 'leak'` and gets 0 rows.

About 5,400 characters, so the cost per question is tiny.

## Providers

| `DDN_LLM` | Needs | Model (`DDN_LLM_MODEL`) |
|---|---|---|
| `openai` (main) | `OPENAI_API_KEY` | `gpt-4o-mini` by default |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` |
| `ollama` | Ollama running locally | `qwen2.5-coder:7b` |
| `offline` | nothing | no LLM |

If `DDN_LLM` is not set, the first configured one is used. All three use **structured output** (a JSON
schema the model must follow), so the code never parses free text. OpenAI: `response_format` with
`json_schema` and `strict: true`.

**Offline mode** maps known question types to fixed Cypher templates. It is a baseline, not GraphRAG, and the
report says so. It exists so `run_all` and the tests work without a key, and it proves the validator, read-only
execution and grounding work end to end. If the LLM call fails during `run_all` (bad key, no credit), it
falls back to offline and the report says why.

## Results (`reports/14_graphrag.md`)

| # | Question | Expected |
|---:|---|---|
| 1 | Water leaks on Line 2 last Tuesday | lot WS-260904-B |
| 2 | Cold welds 7–8 Sep | RB07, WO 4102961 |
| 3 | Paint craters 10 Sep | AHU-TC2, AN-006 |
| 4 | Low wheel-nut torque | NR14, AN-002 |
| 5 | Vehicles with parts from lot WS-260904-B | 1,785 |
| 6 | Oven 2 zone 3 over-temperature | AN-008, false_alarm |
| 7 | Sealer robots for VIN MDDA5XK0XD004375 at station 2 | SR03 and SR04 |
| 8 | Temperature sensors in Oven 2 | 4 tags |
| 9 | Paint film thickness | I don't know |
| 10 | Shift supervisor | I don't know |

Offline: 10/10 (by construction: the templates were written for these questions). Run with your OpenAI key
on the laptop to get the real LLM score. Expect some misses. When one fails, the report shows the Cypher, so
you can see whether the schema prompt or the model was the problem.

## Files

- `src/ddn/graphrag.py`: providers, `validate`, `run_read`, `ground`, `ask`, offline templates, evaluation.
- `apps/ask_app.py`: Streamlit question screen (answer, citations, Cypher, rows), for the demo.
- `tests/test_day9.py`: 18 tests. The LLM is a scripted fake, so it's tested with no key. The tests cover: 8
  kinds of write/procedure attack, an unknown label, relationship or property, keyword-like aliases, a
  rejected-then-retried query, an invented citation being dropped, "can't answer", 0 rows, the full
  evaluation and the screen.

## Limits (say these before someone asks)

- The validator works on text (regex), not a full Cypher parser. The read transaction is the real guarantee
  against writes, and the regex gives the LLM a clear error message.
- Citations prove that a value came from the data, not that the sentence uses it correctly ("RB07 caused it"
  cites RB07 even if the rows say otherwise). The Cypher and rows are shown so a human can check.
- Time-series values are in Parquet, not the graph, so questions like "what was the oven temperature at 3 pm"
  get "I don't know". The next step would be a second tool that reads `store_uri` with `queries.values()`.
- 10 questions is a smoke test, not a benchmark.
