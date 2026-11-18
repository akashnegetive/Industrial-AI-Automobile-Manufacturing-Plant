---
title: "Architecture, Workflow and Graph Structure – Plant DDN-01"
---

# Architecture, workflow and graph structure

**For:** the technical round with the Technical Lead (Ravi Kant Kumar) and a Technical Architect (Info Origin, Dehradun).

An architect does not want to hear every number. They want to see that you can **explain the system as boxes and arrows**, say **why** each box exists, and say **what breaks and how you would scale it**. This guide has three parts, each with a picture you can draw on a whiteboard:

1. **Architecture**: the layers and why each technology was chosen.
2. **Workflow**: the 18 pipeline steps, in order, with what goes in and out.
3. **Graph structure**: how the plant looks inside Neo4j.

At the end: **architect questions with answers**, and a **3-picture whiteboard plan**.

<div class="note"><b>Golden rule for this interview.</b> Start every answer with one sentence of the big idea, then go deeper only if they ask. Architects like short, structured answers: "There are three reasons. One… two… three…"</div>

## The one-minute story

<div class="say">"A car plant keeps its data in many separate systems: SAP has the machines, the historian has the sensor tags, MES has the cars, and maintenance has work orders written as free text. Each system names the same robot differently, so nobody can answer a simple question like <i>which cars were welded while robot RB07 was faulty?</i><br><br>I built a pipeline that takes all these sources, cleans them, and links every record to one key, the SAP functional location. Linking uses rules first and then a LightGBM model. A confidence gate decides: auto-accept, send to an engineer, or put in a backlog. Everything accepted goes into a Neo4j knowledge graph, and every edge records <i>how</i> it was made and how sure we are. On top of the graph I run anomaly detection and a GraphRAG assistant that answers questions with citations."</div>

# Part 1 – Architecture

<!--FIG:architecture-->

Read the picture **left to right**. Data flows from the plant systems on the left to the people on the right. Six layers:

| # | Layer | What it does | Technology | Why this choice |
|---|---|---|---|---|
| 1 | **Sources** | The 9 raw inputs: SAP assets, historian tags, 1-minute time series, MES/RFID reads, torque and part lots, defects, work orders, alarms, drawings and manuals | CSV / PDF files in `data/raw/` | That is what the data pack gives. In a real plant these would be connectors (OPC UA, SAP OData, MES database) |
| 2 | **Ingest / staging** | Read every file, check types, fix units (°F → °C), split tag names by ISA-5.1, repair missing parent assets | pandas, **pydantic** schemas, **Parquet** | Pydantic fails loudly on bad rows. Parquet is fast, typed and columnar, so the later steps load in seconds |
| 3 | **Contextualize** | Link every record to its asset: entity matching for tags and work orders, text and OCR for documents, MES stations and feeds, VIN traceability, anomaly detection | scikit-learn TF-IDF, **LightGBM**, spaCy, Tesseract OCR | Small, explainable models that run on a laptop. No GPU needed |
| 4 | **Gate** | Every link gets a confidence score. Three bands: **auto-accept**, **review**, **backlog**. Backlog items get link-prediction suggestions | Thresholds learned from out-of-fold scores, **Streamlit** review screen | A wrong link is more costly than a missing one, so the auto band must be ≥ 99.5 % precise |
| 5 | **Store** | The graph with provenance on every edge; sensor values stay in Parquet; engineer decisions in `decisions.csv` | **Neo4j 5** (Docker), Parquet | Graph for relationships, columnar files for big numbers. Do not put 1-minute values inside the graph |
| 6 | **Use** | The 7 graph queries (D1–D7), GraphRAG "ask the plant", review screen, demo CLI | Cypher, OpenAI gpt-4o, Streamlit | People and AI both use the same graph |

### The feedback loop (green dashed line)

Every time an engineer approves, rejects or corrects a link on the review screen, the decision is written to `decisions.csv`. On the **next run**:

- the decision becomes a **graph edge** with `method = engineer`, confidence 1.0 (approve / correct replaces the link, reject removes it). For a quick update without a full reload: `python -m ddn.graph --decisions`;
- it also becomes a **new training label** for LightGBM.

So the system gets better with use. This is the same idea as Cognite's "confirmed matches are applied before model predictions".

### Orchestration (dark bar at the bottom)

- `src/ddn/pipeline.py` holds the **step list**. One command runs everything: `make all` on Mac/Linux, `run_all.bat` on Windows.
- Neo4j runs in **Docker** (`docker compose up -d`, image `neo4j:5.26-community`, data in a named volume).
- After the steps, **102 pytest tests** run. Graph tests are skipped if Neo4j is not running.
- If Neo4j is down, the pipeline still runs the first 15 steps and prints that the 3 graph steps were **skipped**. It does not crash.

<div class="say">"I separated the system into layers so each one can be replaced. For example, if the plant moves to Cognite, layers 1–4 stay the same and only the loader in layer 5 changes, because the ontology is written in a YAML file, not inside the code."</div>

## Key design decisions (the "why" an architect will ask)

**1. One canonical key: the SAP functional location.** Example `DDN1-BIW-L2-ST04-RB07` = plant DDN1, shop Body-in-White, line 2, station 04, robot 07. Every other ID (historian tag, MES station, a name written in a work order) is linked **to** it. Why SAP? It is the system maintenance already trusts and it already has the hierarchy.

**2. Ontology first.** `ontology/ontology_v1.yaml` (version 1.3) lists the 18 node types and 19 edge types with their allowed from→to pairs. The **loader**, the **validation** and the **GraphRAG schema prompt** are all generated from this one file. Changing the model = editing YAML + a changelog line, not code in three places.

**3. Provenance on every edge.** Every relationship stores five provenance fields: `source_system`, `method` (source_key, rule, fuzzy, ml, engineer, inferred, derived), `confidence`, `created_at` and `status` (approved / suggested / rejected, the same idea as Cognite's annotation status). Allowed values are listed in the ontology and checked after load. Result: **0 edges without provenance**. Why: an engineer must be able to ask "why does the graph say this?" and the answer must be on the edge.

**4. Thresholds chosen by cost, from data.** Auto-accept only where out-of-fold precision ≥ 0.995 (work-order threshold 0.932, tags 0.50). Backlog below the score where the top candidate was mostly wrong (0.093 for work orders). Between them: human review. The numbers come from the data, not from a guess.

**5. Time-valid edges.** Assets move. Robot RB12 moved from line 1 to line 2 in March 2026. The old `partOf` edge gets `valid_to`, the new one `valid_from`. A car built in February is linked to line 1. Without this, traceability gives wrong answers.

**6. Values outside the graph.** The graph has a `TimeSeries` node (tag name, unit, `store_uri`). The actual 1-minute values stay in Parquet. A graph is good at relationships, bad at millions of numbers. Cognite and AWS TwinMaker do the same.

**7. LLM safety in code, not in the prompt.** GraphRAG Cypher is checked against the ontology, forbidden words (CREATE, MERGE, DELETE, SET, CALL …) are blocked, and the query runs in a **read-only transaction** (`execute_read`). Every sentence of the answer must cite IDs that appear in the result rows.

# Part 2 – Workflow (the 18 steps)

All steps are in `src/ddn/pipeline.py`. Each step is a Python module with a `main()`; it reads files from the previous steps and writes Parquet plus a Markdown report in `reports/`. Steps are **re-runnable**: running again overwrites outputs, and the graph load uses `MERGE`, so nothing is duplicated.

| # | Step (module) | Assignment part | Input → output, in plain words |
|---:|---|---|---|
| 1 | `profile` | B.1 | Read all 9 files → row counts, columns, nulls, examples (report 01) |
| 2 | `quality` | B.2 | Look for problems → **38 data-quality issues** (°F values, duplicates, clock skew, missing parents…) |
| 3 | `identity` | B.3 | How does each system name things? → **9 identity schemes** and how to map them |
| 4 | `problems` | B.4 | Find the **9 production problems** hidden in the data (bad weld current, oven drift…) |
| 5 | `ontology` | D | Check the YAML ontology is valid, write `docs/ontology.md` |
| 6 | `tags` | C1 | Build the **staging tables**: clean assets, tags parsed by ISA-5.1, units fixed |
| 7 | `evaluate` | C | **Rules baseline**: regex / exact-key matching, scored on TRAIN labels |
| 8 | `match_ml` | C | **ML matcher**: blocking (TF-IDF top-15) → 23 pair features → LightGBM → out-of-fold scores → three bands |
| 9 | `export` | C | Predictions for the **hidden test set** → `outputs/` with confidence and band |
| 10 | `linkpred` | E3 | **Link prediction**: graph embeddings suggest top-3 assets for backlog records (hit@1 0.82) |
| 11 | `documents` | C5 | Drawings and manuals → tag mentions with page and label (`mentionedIn`); OCR for the scanned drawing |
| 12 | `workorders` | C4 | Free-text work orders (Hinglish too) → **ISO 14224 failure mode** with spaCy rules |
| 13 | `context` | C | MES station ↔ SAP station, `feeds` edges (process flow), alarm → source asset |
| 14 | `trace` | C6 | **VIN traceability**: each car's path through stations, missed RFID reads inferred, parts and lots |
| 15 | `anomaly` | E1 | Find anomalies in signals, judge them, link to equipment, VINs, defects, work orders |
| 16 | `graph` | D | Load everything into Neo4j: constraints, `MERGE` nodes, `MERGE` edges with provenance, then validate |
| 17 | `queries` | D | Run the **7 assignment queries** D1–D7, save results |
| 18 | `graphrag` | E2 | Answer **10 questions** from the graph with citations (+ 5 held-out) |

Then **102 tests** run.

<div class="note"><b>Easy way to remember the order:</b> <b>Understand</b> (1–5) → <b>Clean</b> (6) → <b>Link</b> (7–14) → <b>Detect</b> (15) → <b>Load and use</b> (16–18).</div>

## Zoom in: how one link is made (entity matching)

Example: historian tag `DDN1_BIW_L2_R07_WELDCUR.PV`. Which SAP asset does it belong to?

1. **Normalize** the text: upper case, split on `_ - .`, expand short forms (R07 → RB07).
2. **Blocking**: do not compare against all ~455 assets. A TF-IDF character n-gram index plus a token index gives the **top 15 candidates**. This keeps it fast: 15 comparisons instead of 375.
3. **Features**: for each (record, candidate) pair, about twenty features (**23 exactly**): string similarity, same line, same station number, same equipment type, unit fits the equipment, and so on.
4. **LightGBM** gives a score 0–1. Trained with **GroupKFold** so the same record is never in train and test at once → honest out-of-fold scores.
5. **Gate**: score ≥ threshold → auto-accept; very low → backlog; between → review.
6. **Write** the link as an edge with `method=ml`, `confidence=score`.

Result: tags F1 1.000, work orders F1 0.982, **0 wrong auto-accepted links**.

<div class="note"><b>If they say "your slide says 20 features":</b> "About twenty. The exact number is 23. The list has 24, and an embedding feature is switched off."</div>

## Zoom in: anomaly detection workflow

1. **Robust z-score** for each signal: (value − rolling median) / rolling MAD. Fast baseline lag 12 h, slow 1 day, window 3 days.
2. Flag when z > 6 (or > 3 for a long run) for at least **10 minutes**. Also a **flat-line** rule: no change for ≥ 60 minutes while the line is producing. Torque: per-tool z-score at 10-minute resolution.
3. **Link**: anomaly → equipment (`hasEvent`) → cars that passed during that time (`exposedTo`) → their defects.
4. **Judge** each anomaly:
    - defect rate on exposed cars is ≥ **5×** normal with ≥ 3 cases → **quality problem**;
    - happened during a planned bake/cleaning window → **false alarm**;
    - a work order matches → **equipment problem**.
5. Result: **8 / 8** seeded problems found, 1 judged a false alarm with reasons. Isolation Forest was run only for comparison.

## Zoom in: GraphRAG workflow

Question → **LLM writes Cypher** (gpt-4o, temperature 0, JSON output, schema from the ontology) → **validator** (only known labels and edges, no write words) → **read-only run** in Neo4j → if too few rows, **expand** to neighbours → **LLM writes the answer** from the rows only → **grounding check**: every sentence must cite an ID that is in the rows. No API key → offline template answers, so the pipeline still finishes.

Result: 10/10 on the tuned set, **4/5 on held-out** questions after reading by hand.

# Part 3 – Graph structure of the plant

The graph has **165,706 nodes** and **1,137,011 relationships**, with **18 node types** and **19 edge types**. Think of it as **two halves joined in the middle**:

- the **asset side** (what the plant *is*: machines, sensors, work orders), and
- the **vehicle side** (what the plant *makes*: cars, parts, defects).

They meet at **Station / Equipment** (a car passes through a station and is processed by a machine) and at **AnomalyEvent** (a machine had a problem; a car was exposed to it).

## 3.1 The asset hierarchy (ISA-95)

<!--FIG:hierarchy-->

- Six levels: **Site → Shop → Line → Station → Equipment → Component**, joined by `partOf` (child → parent).
- The functional location **grows by one segment** at each level, so the hierarchy is visible in the key itself.
- Counts: 1 Site, 5 Shops, 23 Lines, 51 Stations, 221 Equipment, 154 Components (partOf edges: 464).
- `partOf` is **time-valid** (`valid_from`, `valid_to`).
- `feeds` (51 edges) is the **process flow**: which station sends parts to which, or which air handler conditions which paint booth. Used for "what is upstream of this problem?"
- **Tool** (10 nutrunners) is not part of SAP's tree, so it hangs off a component with `partOf`.

## 3.2 The asset side – maintenance view

<!--FIG:asset_side-->

| Edge | From → To | Count | Meaning |
|---|---|---:|---|
| `hasTimeSeries` | Equipment/Component → TimeSeries | 1,532 | this machine has this sensor tag |
| `aliasOf` | TimeSeries → TimeSeries | – | two names for the same signal (e.g. renamed tag) |
| `hasEvent` | Equipment/Component/TimeSeries → AnomalyEvent | 15 | an anomaly was found on this signal / machine |
| `raisedBy` | Alarm → asset | 7,917 | this alarm came from this machine |
| `hasWorkOrder` | asset → WorkOrder | 2,846 | maintenance work on this machine |
| `reportsFailure` | WorkOrder → FailureMode | 2,086 | ISO 14224 code (LOO, VIB, ELP…) from the text |
| `mentionedIn` {page, label} | asset → Document | 211 | this tag appears on this drawing, page N |

## 3.3 The vehicle side – quality and traceability view

<!--FIG:vehicle_side-->

| Edge | From → To | Count | Meaning |
|---|---|---:|---|
| `passedThrough` {passed_at, reader_id, inferred, uncertainty_min} | Vehicle → Station/Line | 316,794 | the car was read at this station at this time |
| `processedBy` {start, end, inferred} | Vehicle → Equipment/Component/Tool | 511,182 | this machine worked on this car |
| `containsPart` {fitted_at, fitted_station} | Vehicle → Part | 64,800 | the car has this part |
| `fromLot` | Part → SupplierLot | 64,800 | the part came from this supplier lot |
| `hasTorqueResult` | Vehicle → TorqueResult | 79,855 | one bolt tightening on this car |
| `tightenedBy` | TorqueResult → Tool | 79,855 | done with this nutrunner |
| `hasDefect` | Vehicle → Defect | 675 | quality found a defect |
| `detectedAt` | Defect → Station | 675 | where it was found (end of line / QI) |
| `exposedTo` {basis} | Vehicle → AnomalyEvent | 2,956 | the car was in the machine during the anomaly |
| `causedBy` (red) | Defect → Equipment/Component/AnomalyEvent/SupplierLot | 297 | **root-cause hypothesis**, stored with `status = suggested` |

**Why `passedThrough` and `processedBy` are the biggest:** 7,200 cars × about 44 stations ≈ 317 k station reads, and each read fans out to the machines at that station ≈ 511 k. **15,250 edges are `inferred`**: the RFID reader missed the car, so we filled the gap from the stations before and after, with `uncertainty_min` and lower confidence.

## 3.4 One real path through the graph

<!--FIG:example_path-->

Read it as a story:

1. Car **MDDA5XK00D003924** has defect **D700356** (bad weld, found at BW-017).
2. The defect is **causedBy** anomaly **AN-003** (weld current problem).
3. AN-003 is an event on robot **RB07** (`DDN1-BIW-L2-ST04-RB07`), found on its tag `…_R07_WELDCUR.PV`.
4. The robot has **work order 4102961** ("cap changed"), which confirms an equipment problem.
5. The car was **exposedTo** AN-003 because it was welded in the anomaly window.
6. The car also **containsPart** a door seal from lot WS-260904-B, so we can rule the supplier in or out.

This one path joins **five systems**: MES (car), QMS (defect), historian (tag), SAP (robot), PM (work order). That is the whole point of the project.

<div class="say">"Before the graph, answering 'which cars did RB07 weld while the current was bad, and did they get defects?' needed four exports and a spreadsheet. Now it is a 4-hop Cypher query that runs in milliseconds, and every hop says where it came from."</div>

## 3.5 Counts and provenance

| Node label | Count | | Method on edges | Edges | Avg confidence |
|---|---:|---|---|---:|---:|
| TorqueResult | 79,855 | | `source_key` (exact ID in source) | 668,185 | 0.994 |
| Part | 64,800 | | `derived` (computed, e.g. time join) | 440,768 | 0.95 |
| Alarm | 7,917 | | `inferred` (gap filled) | 15,250 | 0.846 |
| Vehicle | 7,200 | | `rule` (regex / rule match) | 12,642 | 0.963 |
| WorkOrder | 2,968 | | `ml` (LightGBM auto-accept) | 166 | 0.979 |
| TimeSeries | 1,541 | | `engineer` (review decision) | as approved | 1.0 |
| Defect 675 · SupplierLot 246 · Equipment 221 · Component 154 · Station 51 · Line 23 · FailureMode 16 · Document 15 · Tool 10 · AnomalyEvent 8 · Shop 5 · Site 1 | | | | | |

**Why so few `ml` edges (166)?** Most links already have an exact key or a clear rule. ML is used only for the hard, messy part: free-text work orders and odd tag names. That is the right design: use the cheapest reliable method first.

## 3.6 Three views on one graph

| View | Who uses it | Main nodes and edges | Example question |
|---|---|---|---|
| **Maintenance** | maintenance engineer | asset hierarchy, TimeSeries, Alarm, WorkOrder, FailureMode, Document | "Which robots in BIW had the most VIB failures, and where is their drawing?" |
| **Quality** | quality engineer | Defect, causedBy, AnomalyEvent, exposedTo | "Which cars were exposed to AN-003 and how many had weld defects?" |
| **Traceability** | recall / supplier team | Vehicle, passedThrough, processedBy, Part, SupplierLot, Torque | "Which cars have a part from lot WS-260904-B?" |

Same data, different starting node. No copies.

# Part 4 – Questions a Technical Architect may ask

### Technology choices

**Q: Why Neo4j and not a relational database?**
Our questions are **multi-hop**: car → station → machine → anomaly → work order. In SQL that is 4–5 joins on big tables, and a variable-length path ("everything upstream") is a recursive CTE. In Cypher it is one readable pattern, and the graph walks pointers instead of doing joins. Also, the data model changes often (we went to v1.3); adding an edge type in a graph needs no table migration.

**Q: Why not RDF / a triple store (GraphDB, Neptune RDF)?**
RDF is great for standards and reasoning (OWL), but **properties on edges** are awkward (you need reification or RDF-star). We need `confidence`, `method`, `valid_from` on every edge, so a **property graph** fits better. The ontology is still in a file and could be exported to OWL if a customer needs it.

**Q: Why not just use Cognite Data Fusion?**
The assignment asked to build the logic. My design copies the Cognite ideas on purpose: functional-location key, suggested vs approved links, confidence thresholds, values outside the graph. So moving to Cognite means swapping the store layer: staging, matching and the gate stay.

**Q: Why LightGBM and not a deep model or an LLM for matching?**
Small labelled data (hundreds of pairs), tabular features, need for speed and explanation. LightGBM trains in seconds, gives feature importance, and its scores can be calibrated into thresholds. An LLM per pair would be slow, costly and hard to give a precision guarantee for.

**Q: Why Parquet for staging?**
Typed, compressed, columnar, fast to read with pandas. It is also the format a data lake (Delta Lake, Iceberg) uses, so scaling up does not change the format.

### Scalability

**Q: This is one plant for 2 weeks. How do you scale to 10 plants and a full year?**
Rough numbers: 7,200 cars in 2 weeks → about 190 k cars a year per plant → ~2 M cars for 10 plants. `processedBy` would become ~140 M edges.
What I would change:

1. **Do not store every station read as an edge forever.** Keep `passedThrough`/`processedBy` detail in a **lakehouse table** (Parquet/Delta) and keep in the graph only what queries need (car → line, car → defect, exposures). Or keep detail for a hot window (e.g. 90 days).
2. **Partition by plant**: one database / space per plant (Neo4j Enterprise multi-database or Fabric; in Cognite, one space per plant) plus a small shared space for the ontology, suppliers and part numbers.
3. **Incremental loads** instead of full reloads: process only new files since the last run (watermark per source). `MERGE` already makes reloads safe.
4. **Batch writes**: the loader already uses `UNWIND $rows … MERGE` in batches with uniqueness constraints, which is the recommended fast pattern. For a first bulk load, use `neo4j-admin import`.
5. **Matching**: blocking already makes it O(n × 15) not O(n × m). Training is per plant or shared with a "plant" feature.

**Q: What is the slowest part today?**
The VIN traceability and graph load (hundreds of thousands of edges). Fix: incremental processing, `neo4j-admin import` for bulk, and parallel batches per label.

**Q: Real time?**
Today it is batch (files). For streaming: OPC UA / MQTT from the shop floor → **Kafka** → a stream job that does the same staging and matching per message → writes to the graph and the time-series store. Matching of a **known** tag is just a lookup in the accepted-links table, so it is fast. Only **new** tags go through the ML model and the gate. Anomaly detection runs on a sliding window.

### Reliability and failure handling

**Q: What happens if Neo4j is down?**
The pipeline checks the Bolt connection. If it fails, steps 1–15 still run and write their files, the 3 graph steps are **skipped** with a clear message, and the graph tests are skipped. When Neo4j is back, you run again and `MERGE` makes it idempotent.

**Q: What if the LLM API fails or there is no key?**
GraphRAG falls back to an **offline template baseline**, so the pipeline and tests still finish. In production I would add retry with backoff, a timeout, and a "sorry, I could not answer" message rather than a guess.

**Q: How do you stop bad data from reaching the graph?**
Three layers: (1) pydantic models at staging (each parsed tag is a `TagRecord`), (2) the confidence gate, (3) after load, a **validation step** checks every edge against the ontology's allowed from→to pairs and checks that every edge has provenance. Result: 0 violations, 0 edges without provenance. If either is non-zero, a test fails.

**Q: How do you know the model is still good next month?**
Monitor (a) the **share of records in each band**: if review suddenly grows, the input changed; (b) the **rejection rate** on the review screen for auto-accepted links (should stay < 0.5 %); (c) score distribution drift. Retrain with new engineer decisions. Thresholds are recomputed from out-of-fold data each run, not hard-coded forever.

**Q: How do you handle a wrong link that is already in the graph?**
The engineer rejects it on the review screen → `decisions.csv` → on the next run, the edge is removed and the rejection is kept so the model does not suggest it again (like Cognite's rejected list). Because every edge has `method` and `created_at`, you can also find and remove all links from a bad model run with one Cypher query.

### Security

**Q: The LLM writes database queries. Isn't that dangerous?**
Yes, so it is controlled in **code**: (1) a regex blocks write and admin words (CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD, CALL, …); (2) only labels and edge types from the ontology are allowed; (3) the query runs inside `execute_read`, a read-only transaction, so even if something passes, the database refuses writes; (4) in production, use a separate **read-only database user** too.

**Q: Data privacy with OpenAI?**
For this synthetic data it is fine. For real plant data I would use an enterprise tenant (Azure OpenAI in the customer's region) or an on-premise model, send only the rows needed (not the whole graph), and log every question and answer. The design allows swapping the model because the LLM is behind one function.

**Q: Secrets?**
The API key is only an environment variable (`OPENAI_API_KEY`), never in the repo. The Neo4j password in `docker-compose.yml` is for local demo only; in production it would come from a secret manager (Azure Key Vault, AWS Secrets Manager).

<div style="page-break-before:always"></div>

### Deployment and operations

**Q: How would you deploy this for a customer?**

- Package the pipeline as a **Docker image**; run steps with an orchestrator (**Airflow**, Dagster or Azure Data Factory), one task per step, so a failed step can be retried alone.
- Neo4j as a managed service (AuraDB) or Enterprise cluster on-premise with backups.
- Streamlit screens behind company SSO.
- **CI**: on every push run the 102 tests and a small sample pipeline; block merge if precision of the auto band drops below 0.995.

**Q: How do you version things?**
Code in Git; the **ontology has a version and changelog** (v1.0 → v1.3); every edge stores `method`, `source_system` and `created_at`; thresholds are recomputed and reported every run. So you can say "this edge was made by the ML matcher on this date, under ontology v1.3". In production I would add a `run_id` field too.

**Q: How do you test it?**
102 pytest tests: unit tests for parsing (tag names, units, FL), matcher tests (no wrong auto-links on the labelled set), ontology tests (every edge type allowed), graph tests (counts, no orphan edges, provenance present), GraphRAG tests (validator blocks writes).

### Design trade-offs (be honest)

**Q: What would you do differently?**

- Keep high-volume event edges (`processedBy`) in the lakehouse and expose them through the graph only when needed.
- Make the loader **incremental** from the start.
- Evaluate GraphRAG on more questions (only 20 today) and with a stricter automatic check.
- Get real plant data: synthetic names are more regular than real ones, so real accuracy will be lower at first. That is why the review band exists.

**Q: Where is the system weakest?**
Root causes (`causedBy`) are **hypotheses** with `status = suggested`, not facts. 4 of the 8 root-cause work orders wait in review. I say this clearly in the report rather than over-claim.

# Part 5 – The whiteboard plan (3 pictures, 5 minutes)

If they say "draw the architecture", draw these in order. Practise each once on paper.

**Picture 1 – the layers (1.5 min).** Six columns left to right: *Sources → Staging → Contextualize → Gate (3 bands) → Neo4j + Parquet → Queries / GraphRAG / Review.* Draw the feedback arrow from Review back to Contextualize. Say: "Provenance on every edge, values outside the graph."

**Picture 2 – the hierarchy (1 min).** A vertical stack: Site → Shop → Line → Station → Equipment → Component, with the FL growing. Write one FL: `DDN1-BIW-L2-ST04-RB07`. Add a dashed `feeds` arrow sideways and write "time-valid partOf".

**Picture 3 – the two halves (2.5 min).** In the middle draw **Equipment** and **Vehicle**. Left of Equipment: TimeSeries, Alarm, WorkOrder → FailureMode, Document. Right of Vehicle: Station, Part → SupplierLot, Torque → Tool, Defect. Draw **AnomalyEvent** between them: Equipment `hasEvent` → AnomalyEvent ← `exposedTo` Vehicle. Draw the red `causedBy` from Defect. Then trace the example path with your finger: car → defect → anomaly → robot → work order.

<div class="note"><b>If you forget a number,</b> say the rough size and the reason: "about 1.1 million relationships, most of them station passes and machine steps, because every car touches about 44 stations". That shows understanding, which matters more than the exact digit.</div>

# Numbers to remember (architecture round)

| Thing | Number |
|---|---|
| Pipeline steps / tests | 18 steps (15 + 3 graph) / 102 tests |
| Ontology | v1.3, 18 node types, 19 edge types, 3 views |
| Graph size | 165,706 nodes, 1,137,011 relationships |
| Biggest edges | processedBy 511 k, passedThrough 317 k |
| Cars / parts / torque results | 7,200 / 64,800 / 79,855 |
| Inferred (missed RFID) edges | 15,250, avg confidence 0.846 |
| Matching | top-15 blocking, 23 features, LightGBM, GroupKFold |
| Auto-accept rule | out-of-fold precision ≥ 0.995; WO threshold 0.932, tags 0.50 |
| Results | tags F1 1.000, WOs F1 0.982, 0 wrong auto-links; 99.4 % tags, 95.9 % WOs automatic |
| Anomalies | 8/8 found, 1 false alarm; z > 6, ≥ 10 min, lift ≥ 5× |
| GraphRAG | gpt-4o, temp 0, read-only; 10/10 tuned, 4/5 held-out |
| Link prediction (E3) | hit@1 0.82; hard cases hit@3 0.75 |
