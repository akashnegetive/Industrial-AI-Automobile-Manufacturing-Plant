---
title: "Interview preparation – every slide, explained"
subtitle: "Plant DDN-01 · 45-minute presentation + code walkthrough · easy English"
---

::: note
**How to use this guide.** For every slide you get: what is on it, what each word means, what to say (a
short script) and the questions they may ask, with answers. Read it twice: once slowly, once while clicking
through the slides with **View → Notes** open. Do not learn the scripts word for word; learn the *ideas* and say
them in your own words. The numbers are worth remembering exactly (there is a cheat sheet at the end).
:::

# Part 1 – The big picture (learn this first)

## The story in 4 sentences

1. In a car plant, **one machine has many names**: SAP calls it one thing, the sensor system another, the work
   orders a third, and nobody has linked them.
2. I built a pipeline that **links all those names to one machine ID**, using rules plus a machine-learning model,
   and only accepts a link automatically when it is almost certainly right; unsure links go to an engineer.
3. I put everything into a **knowledge graph** (Neo4j), where every link says **where it came from and how sure
   we are** (provenance).
4. On top of the graph I built **anomaly detection** that links each problem to the machine, the cars and the
   repair, and a **question box** (GraphRAG) that answers in plain English with sources, or says "I don't know".

## Three messages to repeat during the interview

- **Working:** it runs end to end with one command; 18 steps, 102 tests; tested on a fresh copy.
- **Measured:** every claim has a number, and the numbers are honest (out-of-fold, held-out questions).
- **Honest:** I state the limits myself before they ask (slide 25).

## Your 30-second introduction (slide 1)

> "Hi, I'm Akash. For this assignment I built a Python pipeline for car plant DDN-01. The same machine has a
> different name in every system, so I link all those records to one asset, load them into a Neo4j knowledge
> graph where every link has its source and confidence, and then use that graph to find production problems and to
> answer questions with sources. It runs with one command on the synthetic data pack. I'll show the results, the
> design choices and the limits, and then walk through the code."

# Part 2 – Words you must know (glossary in easy English)

**Plant words**

| Word | Meaning in easy English |
|---|---|
| Plant DDN-01 | The (made-up) car factory in the assignment. 600 cars a day, 1–14 September 2026. |
| Shop | A big area of the plant: Press, Body (BIW), Paint, Assembly. |
| BIW (Body-in-White) | The body shop, where robots weld the steel body before painting. |
| Line / Station | A line is a chain of stations; a station is one stop where work is done on the car. |
| Functional location (FL) | SAP's address for a place in the plant, e.g. `DDN1-BIW-L2-ST04-RB07` = plant DDN1, body shop, line 2, station 4, robot 7. **My one canonical ID.** |
| SAP PM / CMMS | The maintenance system. It holds the list of assets and the work orders. |
| Work order (WO) | A repair or maintenance job written by a technician, often in short Hinglish ("robo ka gun nahi chal raha"). |
| PM / CM / CAL | Preventive maintenance (planned) / corrective maintenance (repair) / calibration. |
| Historian (PI, WinCC, S7) | Systems that store sensor values every minute. Each one names tags differently. |
| Tag | The name of one sensor signal, e.g. `DDN1_BIW_L2_R07_WELDCUR.PV` = weld current of robot 7, line 2. |
| MES | Manufacturing Execution System: which car was at which station, and when. |
| RFID reader | Reads a tag on the car body at a station. Sometimes it misses a read. |
| VIN | Vehicle Identification Number: the car's unique ID. |
| Takt time | The time per car at each station: 2.4 minutes here. |
| Nutrunner | The tool that tightens wheel nuts to a set torque (Nm). |
| Sealer robot | Puts sealant on seams (e.g. the roof ditch) so water cannot get in. |
| AHU | Air Handling Unit: controls temperature and humidity in the paint booth. |
| E-coat | The first paint layer, applied in a bath (dip tank). |
| Supplier lot | A batch of parts from a supplier, e.g. door seals lot WS-260904-B. |
| Recall scope | The list of cars that might have the problem and must be checked. |
| EOL | End of line: the final checks (e.g. water-leak test). |

**Standards**

| Word | Meaning |
|---|---|
| ISA-95 | The standard plant hierarchy: site → shop (area) → line → station → equipment → component. |
| ISA-5.1 | Instrument letter codes: TT = temperature, PT = pressure, FT = flow, IT = current. |
| ISO 14224 | A standard list of failure modes, e.g. LOO = low output, VIB = vibration, AIR = abnormal reading. |
| ISO 3779 | The standard for VINs (in this pack VINs are 16 characters). |
| OPC UA / MQTT | Standard ways for machines to send data. |
| AAS (Asset Administration Shell) | An Industry 4.0 standard "digital ID card" for a machine. |
| RDF / OWL | The semantic-web way to store a graph (triples + formal ontology). |

**Data and ML words**

| Word | Meaning |
|---|---|
| Contextualization / entity matching | Linking records from different systems to the same real thing (the same machine). |
| Blocking | A first, cheap step that keeps only the ~15–25 most likely assets per record, so we don't compare every record with every asset. |
| Blocking recall | How often the right asset survives blocking. If it is dropped here, it can never be found later. |
| TF-IDF (character n-grams) | A way to compare texts by small pieces of letters ("RB0", "B07"), so typos still match. |
| Feature | One number that describes a (record, asset) pair, e.g. "do the line numbers agree?". |
| LightGBM | A fast machine-learning model made of many small decision trees (gradient boosting). |
| Precision | Of the links I made, how many are right. |
| Recall | Of all true links, how many I found. |
| F1 | One number that combines precision and recall (their harmonic mean). 1.0 is perfect. |
| Out-of-fold (OOF) / cross-validation | Split the labelled data into 5 parts; train on 4, test on the 5th, repeat. So every record is scored by a model that never saw its answer. |
| GroupKFold | Cross-validation that keeps all candidate pairs of one record in the same fold, so nothing leaks. |
| PR curve | Precision–recall curve: how precision and recall change as the threshold moves. |
| Threshold / band | A score cut-off. Above it: auto-accept. Middle: review. Very low: backlog. |
| Training labels (TRAIN) | The engineer-confirmed answers given in the pack (35% of tags, 30% of WOs). The rest is the evaluator's hidden test set. |
| Hidden test set | The answers the evaluator kept secret to score my predictions in `outputs/`. |
| spaCy EntityRuler | A rule-based tool that finds equipment names and failure words in text. |
| OCR (Tesseract) | Reads text from a scanned image (one drawing was a scan). |
| Robust z-score | "How unusual is this value?" measured against the signal's own normal level (median) and spread (MAD), so one spike doesn't distort the baseline. |
| MAD | Median Absolute Deviation: a robust measure of spread. |
| Hysteresis | Start an alarm only above a high level (z > 6), and end it only below a lower level (z < 3), so it doesn't flicker. |
| Isolation Forest | A standard ML anomaly detector; I used it only to compare. |
| Lift | How many times more often a defect appears on exposed cars than on other cars. |
| Embedding | A list of numbers that describes a thing, so similar things get similar numbers. |
| GraphSAGE-style aggregation | A node's embedding is built from its neighbours' embeddings (here: an asset gets the average of its linked records). |

**Graph and AI words**

| Word | Meaning |
|---|---|
| Knowledge graph | Things are nodes (robot, car, work order), relationships are edges (car **processedBy** robot). |
| Property graph | A graph where nodes **and edges** can carry properties (time, confidence). Neo4j is one. |
| Neo4j / Cypher | The graph database I used / its query language. |
| Ontology | The schema of the graph: which node types and edge types exist and what properties they have. Mine is `ontology/ontology_v1.yaml`. |
| Provenance | On every edge: source system, method (rule/ml/engineer…), confidence, time and status, so you can ask "why does the graph think this?". |
| Containers vs views (Cognite) | Containers = how data is stored; views = how each role (maintenance, quality…) sees it. |
| Parquet | A compact file format for big tables. Sensor values stay here, not in the graph. |
| LLM | Large Language Model (here OpenAI gpt-4o). |
| GraphRAG | The LLM writes a graph query, the code runs it, and the LLM answers only from the results. |
| Grounding / citation | Every sentence of an answer must point to IDs that are really in the query result. |
| Hallucination | When an AI invents a fact. My design blocks it: no citation, no claim. |
| Temperature 0 | Makes the LLM answer the same way each time (less random). |

# Part 3 – Slide by slide

## Slide 1 – Contextualizing Plant DDN-01

**On the slide:** title, subtitle "From siloed plant records to a trustworthy knowledge graph", your name.

- *Siloed* = each system keeps its own data and doesn't talk to the others.
- *Trustworthy* = every link can be checked (provenance) and wrong links are blocked.

**Say:** the 30-second introduction from Part 1.

**Possible question:** *"Why this title?"* → "Because the main problem is not the data, it's that nothing is
connected. And a graph is only useful if people trust it, so every link says where it came from."

## Slide 2 – Plan for the 45 minutes

**On the slide:** the time plan: 0–5 problem and results, Part A, B, C, D, E, limits, then 13 minutes of live
demo, code and questions.

**Say:** "I'll spend about 30 minutes on slides and keep the last part for a live demo and the code. If you have
questions in between, please ask; I have backup slides."

**Tip:** if they say "skip the slides, show the code", go straight to slide 28 and the demo. Be flexible.

## Slide 3 – One robot, five names

**On the slide:** a table with the same welding robot in five systems.

| System | Name | What to point out |
|---|---|---|
| SAP PM | `DDN1-BIW-L2-ST04-RB07`, equipment 10007731 | the "official" name: my canonical ID |
| PI historian | `DDN1_BIW_L2_R07_WELDCUR.PV` | **R07**, not RB07; **no station** in the name |
| Work order | "R7 gun tip dressing fail, cap changed" | free text, short forms |
| Cell drawing | `RB-207` | means line **2**, robot **07** |
| MES / RFID | station B2-04, reader RD-B2-04 | MES's own numbering: B2 = body line 2 |

Right side: **No shared key** (no common ID across systems) and **Defects never name a machine** (a defect is
logged against a car and an inspection point, never against a robot).

**Say:** "Here is the core problem. This is one physical robot, and it has five names. The historian says R07,
SAP says RB07, the drawing says RB-207, MES says B2-04, and the technician writes 'R7'. On top of that, defects
are recorded only against the car, so to find which machine caused a defect you have to go car → station → time →
machine. Without linking, that takes a week of spreadsheets."

**Possible questions:**
- *"Why choose the SAP functional location as the key?"* → "Every engineer knows it, it already contains the
  ISA-95 path (plant, shop, line, station, equipment), and it doesn't change when a tag is renamed."
- *"What is 'Hinglish'?"* → "Hindi words mixed with English, like 'nahi chal raha' = 'not working'. I translate
  common phrases before matching."

## Slide 4 – What I built

**On the slide:** six steps: Ingest → Block → Score → Gate → Graph → AI.

| Step | What it does (easy English) |
|---|---|
| **Ingest** | Load every file into clean, typed tables (pydantic checks types). Parse tag names into shop/line/equipment/signal. Convert °F to °C. |
| **Block** | For each record keep only the ~25 most likely assets (TF-IDF top-15 + a token index on codes like RB07). |
| **Score** | Rules + a LightGBM model give each (record, asset) pair a probability. |
| **Gate** | High score → auto-accept into the graph. Middle → engineer review. Very low → backlog. |
| **Graph** | Load into Neo4j with provenance on every edge. Sensor values stay in Parquet files. |
| **AI** | Anomaly events linked to machines and cars, and the GraphRAG question box. |

Bottom: **one command** (`run_all.bat` or `make all`), **18 steps, 102 tests**. "Thresholds come from the
precision–recall curve, not from the example values" = I did not copy the 0.6/0.9 from the assignment's
figure; I measured my own.

**Say:** "I go left to right. Two rules hold everywhere: only confident or engineer-approved links go into the
graph, and every edge carries provenance, so anyone can ask why the graph believes something."

**Exact detail if asked:** the slide says "20 features"; the exact number is **23 active features** (24 are
listed in the code; the 24th, a sentence-embedding similarity, is switched off because its model couldn't be
downloaded in my build environment). Say: *"About twenty: 23 to be exact."*

**Possible questions:**
- *"Why pydantic?"* → "To check types when loading, so a broken file fails early with a clear message."
- *"Why not compare every record with every asset?"* → "1,541 × 455 is 700,000 pairs for tags alone; at 10
  plants that explodes. Blocking keeps 25 per record and loses almost nothing (blocking recall 1.000 / 0.999)."

## Slide 5 – Results at a glance

**On the slide:** four numbers.

| Number | Meaning |
|---|---|
| **1.000 / 0.982** | F1 for tag matching / work-order matching, out-of-fold on the training labels |
| **0** | wrong links accepted automatically (precision 1.000 in the auto band) |
| **8 / 8** | all eight problems hidden in the sensor data were found; one was correctly judged a false alarm |
| **4 / 5** | unseen GraphRAG questions answered correctly when I read them by hand; it never invented a fact |

**Say:** "Four numbers, and the honest caveat straight away: the matching scores are measured out-of-fold on the
training labels. The evaluator's hidden test set is the real measure, and my predictions for it are in the
outputs folder."

**Possible questions:**
- *"F1 1.000 on tags looks too good."* → "It mostly shows that the synthetic tag names are regular. That's why I
  say it out loud and why the hidden test set is the real measure. Real plants will be messier."
- *"What does 'out-of-fold' mean?"* → see glossary: "each record is scored by a model trained without it".

## Slide 6 – Part A (section title)

**Say:** "First, how real industrial platforms solve this."

## Slide 7 – Three platforms, one pattern

**On the slide:** three columns.

- **Cognite Data Fusion:** *containers* (storage) vs *views* (how each role sees the data); *rules + supervised
  entity matching with a score threshold*; *annotations* with a confidence and a status: suggested / approved /
  rejected.
- **Siemens:** *Insights Hub* builds asset types from *variables* and *aspects*; *IIH Semantics* offers GraphQL
  over a knowledge graph; *Industrial Copilot* generates automation code and helps diagnose faults.
- **AWS IoT TwinMaker:** twins are *entities* with *components*; relationships become graph edges; you query with
  *PartiQL MATCH* and variable-length paths; values stay in *SiteWise / Timestream*.

Bottom, **what I borrowed:** rules and confirmed matches before ML; confidence + status on every link; engineer
decisions reused as training labels; the container/view split; values outside the graph.

**Say:** "Cognite is the most explicit about predicted links and confidence; Siemens and AWS mostly *configure*
links instead of predicting them. From Cognite I took the rules-before-ML order, the confidence and status on
every link, and reusing engineer decisions as labels, which Cognite calls refit. From all three: sensor values stay
outside the graph. Every claim is cited in docs/part_a_research.md, and I checked all 34 links myself."

**Possible questions:**
- *"What did you NOT find?"* → "No named Cognite automotive customer case; and at Siemens, AAS support is a separate
  product, SITRANS assetfox, not part of Insights Hub."
- *"What is GraphQL / PartiQL?"* → "Query languages: GraphQL is used for APIs, PartiQL is AWS's SQL-like language
  that can also match graph patterns."
- *"Why not just use Cognite?"* → see slide 26 (trade-offs).

## Slide 8 – Part B (section title)

**Say:** "Before building anything, I studied the data."

## Slide 9 – 38 data-quality issues, 15 not documented

**On the slide:** a bar chart of issues per dataset (grey = already in the data dictionary, orange = new, found by
my profiling) and six examples.

| Example | Why it matters |
|---|---|
| Relocated robot keeps its old tag name | Robot RB12 moved from line 1 to line 2 in March 2026; its tag still has the old name, so pure name matching gives the wrong line. |
| °F and °C in one historian | Oven temperatures in WinCC are in °F; you can't compare them with °C without converting. |
| Stuck sensor and a 3 h outage | A flat line looks like "everything is fine" but is a broken sensor. |
| 815 alarms write S3 for ST03 | The alarm system abbreviates stations differently. |
| SAP failure codes contradict the WO text | The code says one thing, the technician's text another. |
| Lot id reused across two fitting sessions | Supplier lot WS-260904-B was used on 4 September **and** again on 8–10 September. |

**Say:** "I found 38 issues, each with a count and examples you can check in reports/02; 15 were not in the
data dictionary. The important ones come back later: the relocated robot explains matcher errors, and the reused lot
id changes the recall scope."

**Possible questions:**
- *"How did you find them?"* → "A profiling step for every file: keys, duplicates, missing values, time coverage,
  units, naming patterns. Then specific checks per dataset."
- *"Which issue would hurt most in production?"* → "The reused lot id, because it changes who gets recalled."

## Slide 10 – Nine real production problems

**On the slide:** the nine problems I found in the two weeks.

| Column | Meaning |
|---|---|
| Exposed VINs | Cars that went through that machine during the bad time window |
| Defective exposed / not | Cars with the matching defect among exposed cars / among all other cars |
| Lift | How much more often exposed cars have the defect. "all" = only exposed cars had it |

Key rows:
1. Press line 1 die set-up error → split panels (28 / 0).
2. Nutrunner NR14 offset → low wheel-nut torque (37 / 0).
3. Robot R07 weld-current drift → cold welds (101 / 6, 174×).
4. **Door-seal lot WS-260904-B → water leaks (85 / 0)**: no sensor shows this; only part genealogy finds it.
5. Sealer SR03 heater failure → roof-ditch leaks (2,409×).
6. Booth B humidifier stuck open → paint craters.
7. **Oven 2 zone 3 over-temperature: a false alarm** (no extra defects).
8. AHU TC1 fan bearing wear: caught before failure.
9. E-coat sensor TT-301 frozen: a sensor fault, not a process problem.

**Say:** "My method: find the anomaly window, find the cars that passed that machine in the window, and compare
their defect rate with all other cars. Number 4 matters most: the lot id was reused, so a recall by lot id alone
would include 293 good cars. And number 7 shows not every alarm is a problem."

**Possible questions:**
- *"What's a cold weld?"* → "A weld that didn't fuse properly, here because the weld current was too low."
- *"Why is lift 'all' and not a number?"* → "No non-exposed car had the defect, so the ratio is infinite."

## Slide 11 – Part C (section title)

**Say:** "Now the core: the contextualization pipeline."

## Slide 12 – Match: block, score, gate

**On the slide:** four steps.

1. **Block:** 375 → ~25 candidates per record. Blocking recall 1.000 for tags, 0.999 for work orders.
2. **Features:** "20 per pair" (exactly 23 active): TF-IDF similarity, fuzzy name / FL match, equipment, line,
   station and component agree or conflict, unit fits the equipment type (kA fits a weld gun, Nm a nutrunner), rule
   match and rule confidence, SAP equipment number match, equipment number agrees with the text, valid at the
   record's time (relocation), number of equipment candidates, is-component.
3. **Model:** LightGBM, scored with GroupKFold out-of-fold: no record is scored by a model that saw its label.
4. **Gate:** threshold from the precision–recall curve: precision ≥ 0.995 and no wrong-machine error in the auto
   band.

**Say:** "Blocking matters because if the right asset is dropped here, it can never be found later, so I report
blocking recall. I score out-of-fold so no record is graded by a model that trained on it. And I set the threshold by
the cost of a wrong link, not by maximising F1."

**Possible questions:**
- *"Why LightGBM, not a neural network?"* → "Tabular features, about 1,400 labelled records: gradient-boosted
  trees are strong, fast and explainable (feature importance). A neural net would need far more labels."
- *"LightGBM settings?"* → "300 trees, learning rate 0.05, 15 leaves, minimum 10 samples per leaf, 90% row and
  column sampling."
- *"What's the most important feature?"* → tags: rule match and rule confidence, then fuzzy name/FL; work orders:
  SAP equipment number match, rule match, equipment match (see reports/06).
- *"What is a wrong-machine error?"* → "Linking to a different machine (e.g. robot 7 on line 1 instead of line 2).
  A near miss is the right machine at the wrong level (the robot vs its own weld gun): less harmful."

## Slide 13 – Rules vs ML: where each fails

**On the slide:** F1 bars: tags 0.987 (rules) → 1.000 (ML); work orders 0.950 → 0.982.

- **Rules fail on noise:** typos like `DD1_` instead of `DDN1_`, glued sub-units like `PR2LUB` (press 2
  lubrication), Hinglish text with no code.
- **ML fails on ambiguity:** "RB01 gun water leak" doesn't say which line; robot vs its weld gun.
- **ML fixed 14 tags and 51 work orders the rules missed, and broke none.**

**Say:** "I keep the rules as a baseline and as a feature for the model. Rules are precise but brittle; the model
handles noise. What's left are genuinely ambiguous records, which is exactly what the review band is for."

**Possible question:** *"Why keep rules at all?"* → "They're explainable, they're right when they fire
(precision 1.000 on tags), and they give the model a strong feature. It's also what Cognite does."

## Slide 14 – Threshold set by the cost of a wrong link

**On the slide:** bars: wrong auto-links at thresholds 0.50 → 4, 0.70 → 3, 0.80 → 2, 0.90 → 1, **0.932 → 0**, 0.95 → 0.

- **Why:** a wrong link sends a recall investigation to the wrong machine.
- **Auto band:** 95.7% of labelled work orders linked automatically with 0 errors.
- **Three bands:** auto · review (9 tags, 70 work orders) · backlog (52 work orders, threshold from the data).
- Engineer decisions become `method=engineer` edges **and** new training labels.

**Say:** "I chose the threshold by cost. A wrong automatic link is much worse than a link waiting for a person,
so I took the lowest score where out-of-fold precision is at least 99.5% and there's no wrong-machine error:
0.932 for work orders. Below a second threshold, also read from the data, links go to a backlog: of the six
labelled work orders that low, only one was right. Tags have no backlog because even their lowest scores were
right."

**Possible questions:**
- *"Why 0.995 and not 0.99?"* → "It's a business choice: in a recall, one wrong machine wastes days. I'd agree
  the number with the plant's quality team."
- *"The threshold rests on few errors."* → "Yes, that's on my limits slide; one more error would move it. With
  more labels it gets stabler."
- *"What happens to backlog items?"* → "They are not offered for approval because they're mostly wrong; the fix
  is better source data. But a backlog work order that explains an anomaly is pulled into review, and the others
  get link prediction's top-3 suggestions (slide 24)."

## Slide 15 – One work order, raw text to graph edge

**On the slide:** WO 4102961: *"R7 gun tip dressing fail, cap changed"* / *"Weld current low aa raha tha since
yesterday. L2 ST4 robot 7. Tip dresser blade chipped…"*

1. **Normalise:** Hinglish → "current low"; ST4 → ST04; "R7" / "robot 7" → RB07.
2. **Extract:** tokens L2 · ST04 · RB07 + components WG (weld gun), TD (tip dresser); ISO 14224 failure mode
   LOO (low output).
3. **Match:** the top candidate is RB07-WG (the weld gun) at 0.034 → backlog band.
4. **Review:** pulled into review and ranked first, because it explains anomaly AN-003.
5. **Edge:** after approval: `method=engineer`, confidence 1.0, reused as a training label.

**Say:** "This is interview question 1. Where can it go wrong? The text names the robot, its weld gun and the
tip dresser, and SAP could hold the order on any of the three, so the model is unsure and it is not
auto-accepted. Because it explains a detected anomaly, it is shown first to the engineer. Other risks: a wrong
line when the text doesn't say one, misread Hinglish, and SAP failure codes that contradict the text."

**Possible question:** *"Isn't 0.034 a failure of your model?"* → "It's the model being honest: the text really
is ambiguous between three assets. That's the point of the gate: unsure links go to a person, not into the graph."

## Slide 16 – Part D (section title)

**Say:** "Now the knowledge graph."

## Slide 17 – Ontology first, provenance on every edge

**On the slide:**

- **18 / 19:** 18 node types, 19 edge types, in a versioned YAML ontology (v1.3).
  - Nodes: Site, Shop, Line, Station, Equipment, Component, Tool, TimeSeries, WorkOrder, FailureMode, Document,
    Alarm, AnomalyEvent, Vehicle, Part, SupplierLot, TorqueResult, Defect.
  - Edges: partOf, hasTimeSeries, hasWorkOrder, reportsFailure, mentionedIn, feeds, passedThrough, processedBy,
    containsPart, fromLot, hasTorqueResult, tightenedBy, hasDefect, detectedAt, causedBy, raisedBy, hasEvent,
    exposedTo, aliasOf.
- **165,706 nodes, 1.14 M relationships, 0 edges without provenance.**
- Example edge `(RB07)-[:hasTimeSeries]->(TimeSeries)` with source_system PIPELINE, method rule, confidence 1.0,
  status approved, created_at, evidence "rules (exact) and ML agree".
- **Property graph (Neo4j):** path questions with properties on edges; maps onto Cognite DMS.
- **Time-valid partOf:** robot RB12 moved from L1 to L2; old cars keep the old line.
- **Values in Parquet:** the graph holds a `store_uri` pointer to the sensor values.

**Say:** "I defined the ontology first, in a YAML file, and the loader enforces it: an edge between the wrong
node types is rejected. Every edge has provenance, and the load checks there are zero edges without it. I chose a
property graph because my questions are paths with properties on the edges (time, confidence), and Cypher is easy to
validate, which matters for the AI part. Sensor values stay in Parquet; the graph only points to them."

**Possible questions:**
- *"Property graph or RDF?"* (official question 2) → "Property graph: edge properties are native, Cypher is easy
  to validate, and it maps onto Cognite. RDF/OWL would win for sharing semantics across companies, such as AAS or
  supplier data."
- *"A robot moves from line 2 to line 3?"* (official question 5) → "partOf has valid_from and valid_to. The old
  edge is closed, a new one is opened, and a query for a car uses the edge that was valid at the car's time."
- *"Containers vs views in your design?"* → "One storage schema, and three role views in the ontology file:
  Maintenance, Quality, Traceability."
- *"Why not store sensor values in the graph?"* → "1.1 million values for 55 tags in two weeks; graphs are bad at
  time series. All three vendors keep values outside the graph too."

## Slide 18 – Queries that answer plant questions

**On the slide:** three of the seven required queries.

- **D3 · Calibration gap:** NR14 had no calibration work order in 12 months, one of only 2 of 20 nutrunners. It's
  the one that drifted.
- **D5 · Recall scope:** the lot id gives 1,785 vehicles; using the fitting time narrows it to 1,492, sparing 293
  good cars.
- **D7 · Plant head:** 1,492 + 647 + 106 + 37 cars carried a known risk; inspection caught only part of them.

**Say:** "I chose these three because they are real decisions: a calibration plan, a recall scope, and how good
inspection is. All seven queries, with the Cypher and the real output, are in reports/12 and the report's
appendix, and I can run any of them live."

**Possible question:** *"Run D1 live."* → In the Neo4j browser first set the parameters
(`:param {oven: 'DDN1-PNT-OV2', as_of: localdatetime('2026-09-15T00:00:00')}`), then run the D1 Cypher from
reports/12. Expect the 4 oven-2 temperature sensors.

## Slide 19 – One VIN, end to end

**On the slide:** car MDDA5XK00D003924, Hatch 1.2 MT, 8 Sep 2026: body start 08:55 on BIW line 1 → 40 weld
robots → 6 sealer + 10 paint robots → 11 torque joints, all OK → 9 parts with lots, including door-seal lot
WS-260904-B → end-of-line audit at 20:00, 44 stations. Defect D700356 BW-017 (weld nugget small) → causedBy
AN-003 on robot RB07 (derived, confidence 0.9) → fixed by WO 4102961.

**Say:** "This is the second story of my demo video. Every line is one graph query. Missed RFID reads are filled
in from takt time and flagged as inferred; I validated that by hiding 5,793 real reads: the median error was 0.28
minutes."

**Possible questions:**
- *"What if the inferred time is wrong?"* → "After buffers it can be up to 69 minutes off, so each inferred passage
  stores an uncertainty and gets a lower confidence. It's on my limits slide."
- *"Why confidence 0.9 on causedBy?"* → "It's a derived hypothesis from defect lift, not a measured fact, so it is
  below 1.0."

## Slide 20 – Part E (section title)

**Say:** "Last part: AI on top of the graph."

## Slide 21 – 8 anomalies, judged in context

**On the slide:** a table of 8 events and their verdicts (5 quality problems, 1 equipment problem, 1 sensor
fault, 1 false alarm), plus how it works:

- **Robust z-score** against each signal's own lagged 3-day median/MAD, only while the line is producing.
  Alarm starts at |z| > 6, continues while > 3, minimum 10 minutes. A fast version (12 h lag) for sudden events
  and a slow one (1 day lag) for drifts. Plus a flat-line detector (same value for 60+ minutes while running) and a
  per-tool torque z-score.
- **Written to the graph** on the equipment and the tag, with `exposedTo` edges to the cars.
- **Judged** by defect lift (≥ 5× with ≥ 3 cases = quality problem), a confirming work order, and the bake window
  from the oven manual.
- **Isolation Forest only as a comparison:** it flagged more windows (13) with less meaning.

**Say:** "I didn't use fixed limits. Each signal is compared with its own normal behaviour. Then the important
part: each alarm is judged in context. AN-008 is the false alarm: the oven over-temperature was real, but under 2
hours and under +30 °C, which is inside the bake window in the manual, and the cars in the oven had no extra
defects. AN-007 is a data problem: the sensor froze while the line was running."

**Possible questions:**
- *"Why 'lagged' median?"* → "So the baseline is from the past and the anomaly itself doesn't pull the baseline
  up and hide itself."
- *"Why not Isolation Forest?"* → "It gives a score but no reason, and it flagged more windows. A robust z-score per
  signal is explainable to an engineer: 'this value is 9 spreads away from its normal'."

## Slide 22 – GraphRAG: grounded or silent

**On the slide:** Question → LLM writes Cypher → Validate → Read-only run → Cited answer.

- **Validator:** no write keywords (CREATE, DELETE, SET…); labels, relationships, properties and arrow directions
  checked against the ontology; EXPLAIN (syntax check); LIMIT added.
- **No citation, no claim:** every cited ID must appear in the result rows, or the sentence is dropped.
- **Three ways to "I don't know":** the schema can't answer · the query returns 0 rows · nothing survives grounding.
- **LLM:** OpenAI gpt-4o, temperature 0, structured JSON output; Claude, Ollama and an offline mode can be
  switched in.

**Say:** "The safety is in code, not only in the prompt. Neo4j's read-only transaction is the real guard against
writes, and my validator gives the model a precise error message for one retry. The answer must cite IDs that are
really in the results, so it can't invent facts."

**Possible questions:**
- *"Can someone delete data with a clever question?"* → "No: the query runs in a read-only transaction; Neo4j
  itself refuses writes. The keyword check is an extra layer."
- *"Why gpt-4o?"* → "I had an OpenAI key; gpt-4o-mini scored 2/10, gpt-4o was much better. The provider is a
  setting."
- *"Is sending plant data to OpenAI OK?"* → "For synthetic data, yes. For a real plant, no: I'd use Azure OpenAI in
  the company's tenant or a local model. That's on my limits slide."

## Slide 23 – The evaluation drove the design

**On the slide:** correct answers out of 10 per run: 2, 7, 8, 10, 8, 10. **4/5 on unseen questions, read by
hand** (the automatic check said 5/5). No answer in any run contained an invented fact.

**The story (learn it, it's a strong one):**
1. Run 1: gpt-4o-mini, a thin prompt → **2/10**. It gave up too early and guessed relationship directions.
2. Run 2: gpt-4o + real relationship patterns from the data + worked examples + a direction check + retry on empty
   results → **7/10**.
3. Run 3: smaller fixes → **8/10**.
4. Run 4: the supplier-lot cause was **missing from the graph itself**; I added it → **10/10**.
5. Run 5: a first held-out set scored **2/5**: I had overfitted to the 10 questions. Also some randomness → fixed with
   temperature 0.
6. Run 6: fixes only by **failure type**, and a **fresh** held-out set → 5/5 automatically, but when I read the
   answers one led with a routine PM order instead of the real repair, so I count **4/5**.

**Say:** "The evaluation drove the design. And when the held-out set showed overfitting, I stopped tuning on single
questions. The honest unseen score is 4 out of 5. And in every run, every failure was 'I don't know' or a real
record in the wrong order; no answer ever invented a fact."

**Possible question:** *"Why not 5/5?"* → "My automatic check only tested that the expected ID appears somewhere.
Reading the answers, I saw one answer put a routine PM order first. A stricter grader, like an LLM judge, is the
next step."

## Slide 24 – E3 bonus: link prediction

**On the slide:** a table: all labelled records hit@1 0.82, hit@5 0.97; hard records (matcher unsure or wrong)
hit@1 0.30, **hit@3 0.75**, hit@5 0.85. Example WO 4100629 "Station 04 L2 fixture locating pin worn": the matcher
guessed a conveyor (0.002), link prediction says `DDN1-BIW-L2-ST04-FX` (the right fixture).

- *hit@3* = the right asset is among the top 3 suggestions.
- **Asset embedding** = its own tokens + the average of the records already linked to it (GraphSAGE-style).
- **Used for the backlog only:** top 3 to the review screen, never auto-accepted.
- **First try (SVD embedding):** hit@1 0.03, replaced, and I report it.

**Say:** "This is the bonus. Link prediction learns from the graph: work orders that use the same words as those
already linked to an asset are probably about that asset. My first version, a spectral embedding, failed with 3%
because sibling robots on different lines share the same words; averaging the approved links fixed that. It's
weaker than the matcher overall, so I only use it as a top-3 short list for the backlog. Two settings were picked
on the same data, so its numbers are slightly optimistic."

**Possible question:** *"Is this a real GNN?"* → "No, it's a parameter-free version of the idea (one round of
mean aggregation, no learned weights). A trained GNN, for example in PyTorch Geometric, would be the next step."

## Slide 25 – Limits I state up front

| Limit | What it means |
|---|---|
| Synthetic, TRAIN-only scores | Measured on the training labels; the hidden test set is the real measure. |
| Thresholds from little data | One more error would move the work-order threshold. |
| Root causes in review | 4 of the 8 root-cause work orders still wait for an engineer. |
| Inferred reads after buffers | Up to 69 minutes off; flagged with an uncertainty. |
| Causes are hypotheses | The lot cause needs a defect-to-part map (WL-104 leak at the door → door seal). |
| GraphRAG: lenient check, OpenAI | Automatic 5/5 was 4/5 by hand; data is sent to OpenAI. |

**Say:** "I'd rather say these myself. The biggest one: all my scores are on the training labels, and synthetic
names are more regular than real ones."

**Official question 4 – "Why might real data score lower, and how would you find out?"** → "Real naming is less
regular, labels are noisier, and new lines appear. To find out, I'd label a random sample of about 200 records per
source and per plant, compare with my scores, and track the precision of auto-accepted links every month."

## Slide 26 – At 10 plants and 2 M VINs a year

- **Split the storage:** the graph keeps assets, tags, work orders, defects, lots and anomalies; the per-station
  passages (about 80 million a year) go to partitioned Parquet/Delta files, like sensor values.
- **Per-plant matching:** parsing rules become per-plant configuration; retrain per plant with active learning
  (the engineer reviews the most useful items first).
- **Stream and govern:** OPC UA / MQTT → Kafka; real MES times replace the takt-time guess; a versioned ontology
  with an owner; the LLM runs inside the company's own cloud tenant.
- **In Cognite:** spaces + DMS for the structure, the time-series API for values, Atlas AI for agents. The design maps
  one to one.

**Say:** "At scale I wouldn't put 80 million passages a year into the graph; they'd go to columnar files, and the
graph keeps the things people ask about."

**Official question 7 – "How does your design map onto Cognite, and what would you lose with your own stack?"** →
"Ontology = containers + views; functional location = externalId; provenance = annotation confidence and status;
Parquet = the time-series API. With my own stack I lose Cognite's managed extractors, diagram parsing, access
control and Atlas AI; I gain transparency, cost control and no lock-in, but I have to operate it myself."

## Slide 27 – Live demo: four things to show

1. `python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV`: raw tag → parsed → matched → graph edge with provenance.
2. `python -m ddn.demo vin`: one car end to end.
3. Review screen: search 4102964 (or another undecided one), approve, `python -m ddn.graph --decisions`, the same
   Neo4j query before and after.
4. Ask screen: the cold-weld question, open the Cypher expander, then the shift-supervisor question → "I don't know".

**If the live demo fails:** stay calm, say "this is exactly why I recorded it", and play the video
(youtu.be/86zMkBF6CfI). Before the interview: `git pull`, `run_all.bat` once, start Docker/Neo4j, open both Streamlit
screens, set `$env:PYTHONPATH = "src"` in the demo window, and check the ask screen says **Mode: openai**.

## Slide 28 – Code walkthrough: where to look

| File | What to show and say |
|---|---|
| `src/ddn/pipeline.py` | "One list of 18 steps, used by both `make all` and `run_all`." |
| `src/ddn/match_ml.py` | `CandidateGenerator` (blocking: TF-IDF top-15 + code tokens), `pair_features()`, `cross_validate()` (GroupKFold), `thresholds()` (precision ≥ 0.995, no wrong-machine error; backlog cut-off). |
| `src/ddn/review.py`, `apps/review_app.py` | The review queue, `decisions.csv`, decisions reused as labels; anomaly items first. |
| `ontology/ontology_v1.yaml` | Node and edge types, provenance fields, views, changelog. |
| `src/ddn/graph.py` | `prov()` adds provenance to every edge; `approved_links()`; `validate_graph()` checks provenance and endpoints. |
| `src/ddn/queries.py` | The seven Cypher queries D1–D7. |
| `src/ddn/anomaly.py` | `robust_z()`, `alarm_windows()` (hysteresis), `judge()` (the verdict rules). |
| `src/ddn/graphrag.py` | `validate()` (safety), `run_read()` (read-only), `ground()` (citations), `expand()` (adds context). |
| `src/ddn/linkpred.py` | `LinkPredictor.fit()` averages approved links into asset vectors; `suggest()` ranks assets. |

**For official question 1 (one work order)** open `textnorm.extract`, then the features in `match_ml.py`, then the
review screen. **For "why does the graph think this?"** open `graph.prov` and click an edge in Neo4j.

**Tip:** if they open a file you didn't expect, read the docstring at the top out loud first; every module starts
with a short explanation of what it does and how to run it.

## Slide 29 – Working, measured, honest

**Say:** "To sum up: it works end to end, every result is measured, and I've told you the limits. The code is on
GitHub and the five-minute demo is on YouTube. I'm happy to go into any part in more detail."

## Slides 30 and 31 – Backup: the 7 interview questions

These are the seven questions from the assignment. Full answers are in Part 4 below.

# Part 4 – The 7 official questions (full answers)

**1. "Walk through one work order from raw text to a graph edge. Where could it go wrong?"**
"Take WO 4102961. First I normalise the text: Hinglish to English, ST4 to ST04, R7 and 'robot 7' to RB07. Then I
extract tokens (line L2, station ST04, robot RB07, components weld gun and tip dresser) and the ISO 14224 failure
mode, low output. Blocking gives about 25 candidate assets, the model scores each, and the best is the weld gun of
robot 7, but only at 0.034, because the text names the robot, the gun and the tip dresser. So it goes to the backlog,
but since it explains anomaly AN-003 it is pulled into review and shown first. When an engineer approves it, it
becomes an edge with method engineer and confidence 1.0, and a new training label. It can go wrong when the text
names several assets, when no line is given, when Hinglish is misread, or when SAP's failure code contradicts the
text."

**2. "Property graph or RDF? What changes at 10 plants, 50,000 tags and 2 million VINs a year?"**
"Property graph, because my questions are paths with properties on the edges (time, confidence, provenance), and
Cypher is easy to validate for LLM-written queries. RDF would win for sharing meaning across companies. At that scale
I'd keep assets, tags, work orders, defects, lots and anomalies in the graph, but move the per-station passages
(80 million a year) to partitioned columnar files, keep one graph space per plant with a shared layer for asset types
and supplier lots, and stream data in instead of batch loading."

**3. "How did you set the auto-accept threshold? What does a wrong auto-accepted link cost in a recall?"**
"From the out-of-fold precision–recall curve: the lowest score where precision is at least 99.5% and there is no
wrong-machine error: 0.932 for work orders. A wrong link in a recall sends engineers to the wrong machine and can
exclude the cars that really need checking, which costs days and trust. A link waiting for review costs a few
minutes of an engineer's time. So I tuned for precision, not F1."

**4. "Your matcher scores well on synthetic data. Why might it score lower on real data, and how would you find
out?"**
"Real names are less regular, there are more typos and local habits, labels are noisier, and new lines appear.
I'd label a random sample of about 200 records per source and plant, measure precision and recall there, and
monitor the precision of auto-accepted links every month; a drop means drift."

**5. "A robot is moved from Line 2 to Line 3. How does the graph stay correct for VINs built before and after?"**
"partOf has valid_from and valid_to. I close the old edge at the move date and open a new one. A query for a car
uses the edge that was valid at the car's time, so old cars still trace to line 2 and new ones to line 3. That's
exactly what happened with robot RB12 in the data."

**6. "Which parts did an AI assistant write, and how did you check them?"**
"I used an AI coding assistant as a pair programmer: it drafted most of the code, the tests and the documentation,
and docs/AI_USAGE.md lists every file. I decided the approach and checked it: I ran every step on my own laptop,
compared the outputs with the raw data and with the assignment's numbers, reported every failure I hit and got them
fixed (the git history shows them), and the evaluation itself caught problems: GraphRAG went from 2/10 to 10/10, and
when the held-out set showed overfitting I changed the method. In my demo I approved a link and showed it in the
graph. I can explain any part of the code."

**7. "How does your design map onto Cognite's data modelling service, and what would you lose by using your own
stack?"**
"My ontology is like Cognite's containers plus views; the functional location is the externalId; my provenance is
like an annotation's confidence and status; and the Parquet files are like the time-series API. With my own stack I
lose managed extractors, diagram parsing, access control and Atlas AI. I gain transparency, cost control and no lock-in,
but I have to run and maintain it."

# Part 5 – Other questions they may ask

**About the data and the problem**

- *What was the hardest data problem?* → "Ambiguity in work orders: one text names several assets. And the reused lot
  id, which changes the recall scope."
- *How do you know the 9 problems are real?* → "Each has a time window, the cars exposed, and a defect rate far above
  the rest (lift), and most have a confirming work order."
- *What's the difference between a sensor fault and a process problem?* → "A sensor fault is a data problem (the
  sensor froze); the process was fine. A process problem changes the product (more defects)."

**About matching**

- *Why character n-grams?* → "They tolerate typos: `DD1_` and `DDN1_` still share most pieces."
- *How many labels did you have?* → "539 tags and 888 work orders with engineer-confirmed answers."
- *What if blocking misses the right asset?* → "Then nothing later can fix it; that's why I measure blocking recall
  (1.000 / 0.999) and combine TF-IDF with a token index on codes."
- *How do engineer decisions improve the model?* → "Approved or corrected links are added as training labels for the
  final model on the next run (like Cognite's refit). They are not used in the evaluation, so the scores stay fair."
- *Why didn't you use sentence embeddings?* → "The feature is built in, but the model couldn't be downloaded in my build
  environment, so it's switched off; the other features were enough here. On real free text it would help."

**About the graph**

- *How long does the graph load take?* → "About 3–5 minutes for 1.14 million relationships, with batched writes."
- *How do you make queries fast?* → "Uniqueness constraints and indexes on keys; every query starts from a key (VIN,
  lot, FL), never a full label scan."
- *What is in `evidence`?* → "A short reason, e.g. 'rules (exact) and ML agree | ML p=1.0', or 'engineer decision in the
  review screen'."

**About anomalies**

- *How do you avoid alarms on Sundays or stoppages?* → "The baseline uses only times when the line is producing; Sundays
  are excluded."
- *What's the difference between the fast and slow detectors?* → "Fast (12-hour lag) catches sudden changes; slow (1-day
  lag) catches drifts that build up over days, like the fan bearing."

**About GraphRAG**

- *What happens if the LLM writes a bad query?* → "The validator rejects it with a precise reason and the LLM gets
  up to three tries; empty results also trigger a retry; then 'I don't know'."
- *What's evidence expansion?* → "After the LLM's query, fixed (not LLM-written) queries add the asset and work order of
  any anomaly in the result, so the answer has full context."

**About you and the process**

- *What would you do with one more week?* → "A stricter GraphRAG grader, a trained GNN for link prediction, the
  sentence-embedding feature, and measuring on a real labelled sample."
- *What are you most proud of?* → "That the system is honest: wrong links are blocked, every edge says where it came
  from, and the AI says 'I don't know' instead of guessing."
- *What went wrong?* → "My first link-prediction version scored 3%, and GraphRAG started at 2/10. In both cases the
  measurement showed it and I changed the method."

# Part 6 – Numbers cheat sheet

| What | Number |
|---|---|
| Data | 455 assets, 1,541 tags, 1.1 M sensor values (55 tags), 7,200 VINs, 310,462 RFID passages, 2,968 work orders, 7,917 alarms, 675 defects |
| Labels | 539 tags, 888 work orders |
| Data-quality issues | 38 (15 not documented) |
| Production problems | 9 |
| Blocking | ~25 candidates instead of 375; recall 1.000 tags / 0.999 WOs |
| Features | ~20 (exactly 23 active) |
| F1 rules → ML | tags 0.987 → 1.000; WOs 0.950 → 0.982 |
| ML fixed | 14 tags + 51 WOs, broke none |
| Thresholds (WO) | auto 0.932; backlog below 0.093 |
| Bands (WO) | 2,846 auto · 70 review · 52 backlog |
| Auto-linked | 99.4% of tags, 95.9% of WOs |
| Graph | 18 node types, 19 edge types; 165,706 nodes; 1,137,011 relationships; 0 without provenance |
| VIN inference | 6,332 inferred (2%); validated on 5,793 hidden reads; median error 0.28 min; 95.7% within one takt |
| Recall scope | 1,785 by lot id → 1,492 with fitting time; 293 good cars spared |
| Anomalies | 8 events: 5 quality, 1 equipment, 1 sensor fault, 1 false alarm |
| GraphRAG | 2 → 7 → 8 → 10 → 8 → 10 /10; unseen 4/5 by hand |
| Link prediction | hit@1 0.82; hard cases hit@3 0.75; SVD first try 0.03 |
| Pipeline | 18 steps, 102 tests, one command |

# Part 7 – Interview-day checklist

1. **The night before:** `git pull`, `run_all.bat` (18 steps, 102 tests), rehearse once with a timer.
2. **One hour before:** start Docker Desktop, `docker compose up -d`; open both Streamlit screens (ports 8501 and 8502)
   after the pull; check the ask screen says **Mode: openai**; open the Neo4j browser; set `$env:PYTHONPATH = "src"` in
   the demo window; close email and chat; turn on Do not disturb.
3. **Have open:** the slides (with notes on your own screen), the repo in VS Code, the YouTube video as a backup.
4. **Never show your OpenAI key** on screen.
5. **If you don't know an answer:** say "I don't know that yet, but this is how I'd find out…". That is exactly the
   behaviour your own system has, and interviewers respect it.
