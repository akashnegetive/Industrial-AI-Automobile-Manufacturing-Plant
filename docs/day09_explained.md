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

The validator also checks **relationship directions** against the ontology: `(Defect)<-[:causedBy]-(Equipment)`
is rejected with "causedBy goes (Defect)-[:causedBy]->(…). Check the arrow direction."

A rejected query, or one that returns **0 rows**, is sent back to the LLM with the reason (up to **3 attempts**).
0 rows usually means a wrong guess (wrong direction, `Equipment` instead of `Component`, a misspelt code), not
"the answer is nothing". Rejected attempts are listed in the report.

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

- **The relationship patterns that really exist in the data, with counts** (computed from the live graph), e.g.
  `(:Defect)-[:causedBy]->(:AnomalyEvent) 212`. The ontology says what is *allowed*; this says what is *there*.
- **Six worked examples** (question → Cypher) for the main paths: defect → anomaly → equipment → work order,
  defects on a day with lot and anomaly, lot → vehicles, vehicle → processedBy robots, the asset hierarchy →
  sensors, anomaly verdicts, plus one "can_answer=false". They use **other** entities than the 10 evaluation
  questions (no evaluation answer appears in the prompt) and every example is tested: it must pass the validator
  and return rows.

About 11,000 characters, roughly 3,000 tokens: still a fraction of a cent per question.

## Providers

| `DDN_LLM` | Needs | Model (`DDN_LLM_MODEL`) |
|---|---|---|
| `openai` (main) | `OPENAI_API_KEY` | `gpt-4o` by default |
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

## First real run, and what it taught

The first laptop run with **gpt-4o-mini** scored **2/10**: only the two "I don't know" questions passed. The
report showed why, which is exactly what the report is for:

| What went wrong | Example from the report | Fix |
|---|---|---|
| Gave up too early: said the schema can't explain causes | Q1, Q3, Q6, Q8: `can_answer=false` | Rule: causes ARE in the graph (`causedBy`, `judged`, lots); only say "can't" when the *kind* of data is missing |
| Wrong arrow direction / invented paths | `(d:Defect)<-[:causedBy]-(e:Equipment)`, `(AnomalyEvent)-[:hasTimeSeries]->` | Direction check in the validator + live patterns in the prompt |
| Guessed Equipment vs Component vs Tool | Q7: `processedBy->(t:Tool)` | Use `:Asset` + `asset_type`; list the asset types |
| One wrong query = give up | Q2, Q4, Q7: 0 rows | Retry on 0 rows (3 attempts) |
| Right answer thrown away | Q5: 1 row with 1,785, but the sentence cited the lot ID, which was only in the `WHERE` | Values the query filtered on can be cited when rows come back; `1,785` = `1785` |
| Small model | – | Default model now `gpt-4o` |

Note what did **not** happen: no wrong answer got through. The two questions with no answer in the data gave
"I don't know", and every failure was "I don't know", never an invented fact. The safety design held; the
prompt was too thin.

### Second run: gpt-4o with the better prompt, 7/10

| Miss | Why (from the report) | Fix |
|---|---|---|
| Q1 water leaks, Line 2 | Joined `(v)-[:passedThrough]->(:Line {fl:'DDN1-BIW-L2'})`, but vehicles pass the body line's **stations**; passedThrough to a Line exists only in the paint shop. The 3rd attempt also reused `l` for both Line and SupplierLot, and changed the date | Prompt rule "a vehicle went through a line if it passed one of its stations"; the validator rejects one variable used for two node types; retries must keep the question's dates |
| Q3 craters | Query returned the anomaly but not its asset; the model cited the WO number, which was only inside the `reason` text, so the sentence was dropped | Rule: with an AnomalyEvent, always return its asset and work order. An ID that appears as a whole word inside a text value of the rows can be cited (a fragment like `4102` of `4102963` can't) |
| Q4 nutrunner | Right answer (NR14), but it didn't name the anomaly AN-002 that was in the rows | Answer prompt: name the supporting evidence (anomaly_id, wo_number, lot_id) |

The scoring stayed strict: Q4 still needs the evidence ID, not only the right asset.

### Third run: 8/10, and the two misses were missing *evidence*, not bad Cypher

| Miss | Why | Fix |
|---|---|---|
| Q1 water leaks | The query was right (45 rows: lots of every part on the leaking cars). The model said "I don't know" because battery, windshield and seat lots looked just as common. That's honest: **the graph had no edge saying the door-seal lot is a cause.** Part B found it, but it was never loaded | Load `Defect-[:causedBy]->SupplierLot` (85 edges, `method=derived`, `status=suggested`) |
| Q3 craters | Right anomaly and WO, but the query didn't return the asset (AHU-TC2) | **Evidence expansion**: after the LLM's query, fixed queries add the asset + work order of every anomaly in the rows and the root-cause facts of every lot in the rows ("Related facts" in the screen) |

Why the lot rule needs domain knowledge: a purely statistical rule ("lot with ≥ 3× the defects of the next lot")
also flags the battery, tyre and seat lots of the same days, because a short burst of defects falls into one
lot of *every* part. The fix is a defect → part map (`DEFECT_PART` in `graph.py`): WL-104 is a leak at the front
door upper edge, where the door seal sits. Only then is the concentration test applied. The result is a
hypothesis (`status=suggested`), and the answer has to say so.

Evidence expansion is safe because those queries are fixed code, not LLM-written, and the answer is still
grounded: citations must appear in rows + added facts.

### Fourth run: 10/10, and why there is a held-out set

| Run | Change | Score |
|---|---|---:|
| 1 | gpt-4o-mini, schema-only prompt | 2/10 |
| 2 | gpt-4o, live patterns, examples, direction check, retry on 0 rows | 7/10 |
| 3 | station rule, variable check, anomaly context rule, citing inside text | 8/10 |
| 4 | supplier-lot root cause in the graph, evidence expansion | 10/10 |

**Careful with the 10/10:** the prompt was tuned by looking at failures on these same 10 questions, so the score
is optimistic (the same problem as tuning a model on its test set). That's why `HOLDOUT` has 5 more questions
(roof-ditch leaks, the e-coat sensor fault, the AHU-TC1 fan, vehicles exposed to AN-003, and one "I don't know").
They were written after the tuning and are never used to change the prompt; the report scores them separately.
A test also checks that no expected answer appears in the prompt examples.

### Fifth run: 8/10 and held-out 2/5 with the same code

Two lessons:
1. **10/10 → 8/10 with no code change** = randomness. The OpenAI calls used the default temperature (1.0).
   Now `temperature=0` and a fixed `seed`, so runs are repeatable and a change in score means a change in code.
2. **Held-out 2/5** is the honest number: the tuning fitted the 10 questions better than it generalised. The
   held-out failures are analysed by *category* (not by question), and only general fixes are allowed. After
   that, the held-out set is "used", so a fresh one is needed for a fair score again.

### Sixth change: general fixes from the held-out failures, and a fresh held-out set

Run 5 (temperature 0): tuned 8/10, held-out 2/5. The failures were sorted into **types**, and only general fixes
were made:

| Type | Seen in | Fix |
|---|---|---|
| Asset named by description ("AHU TC2"), not its fl | Q3 | Answer prompt: name assets by fl |
| Ontology allows a path the data doesn't have (`Defect-causedBy->Equipment`) | Q4 | Retry message names hops with **no edges in the data** and lists the ones that exist |
| Two codes with the same description (WL-101 / WL-104 "Water leak") | H1 | Value list shows each code's locations (roof ditch vs front door) |
| Picked a 2025 work order, ignored the asset's anomaly | H3 | Evidence expansion also adds anomalies on assets in the rows; prefer the 1–14 Sep data period; match assets by name if unsure of the fl |
| "sensor fault" marked wrong because the scorer wanted `sensor_fault` | H2 | Scorer treats `_` as a space (a grading fix, not a model fix) |

Because round-1 held-out failures were used to choose these fixes, that set is no longer unseen. **Round 2**
(`HOLDOUT_2`, 5 new questions) was written together with the fixes, before any run. Its score is the one to
quote.

### Final run (run 6, gpt-4o, temperature 0)

| Set | Score | Meaning |
|---|---:|---|
| 10 tuning questions | **10/10** | optimistic: the prompt was tuned on these |
| Held-out round 2 (unseen) | **4/5** on manual review (automatic check: 5/5) | **the number to quote** |
| Held-out round 1 (used for fixes) | 4/5 | was 2/5 before the general fixes |

Tuning stopped here on purpose: more fixes would only fit these questions.

The one remaining miss is a known limitation: the model searched for `name CONTAINS 'TC1 supply fan'`, but the
asset is called "Supply fan AHU-TC1". `CONTAINS` is exact and case-sensitive, so 3 attempts found nothing, and
the answer was "I don't know" rather than a wrong answer. Next step: an entity-lookup tool (a Neo4j full-text
index or the Day 5 fuzzy matcher) that turns "AHU TC1 supply fan" into its fl before the query is written.

**Manual review caught one more miss.** Held-out question 3 ("which work order fixed the sealer robot nozzle
problem?") passed the automatic check because 4102962 appeared in the answer, but the answer *led* with a
routine PM order (4102593, "SL SR01 PM: dispenser check, nozzle replace") and gave the real repair second. The
automatic check only tests that the expected IDs appear somewhere; it can't see which one the answer presents as
the answer. Honest score: 4/5. Next step would be a stricter grader (LLM judge, or check the first claim).

**In one sentence for the interview:** no answer in any run contained an invented fact (every cited value came
from the graph); the failures were "I don't know" or, once, the wrong real record first, and reading the answers
by hand caught what the automatic check missed.

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
- `tests/test_day9.py`: 28 tests. The LLM is a scripted fake, so it's tested with no key. The tests cover: 8
  kinds of write/procedure attack, an unknown label, relationship or property, wrong arrow directions, citing counts and filter values, the prompt examples, keyword-like aliases, a
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
