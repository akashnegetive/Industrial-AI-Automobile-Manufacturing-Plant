# Learning Guide – Plant DDN-01 Knowledge Graph Assignment

Read this first. It explains **what the assignment is**, **what you need to learn**, and **how we build it over 10 days**.

---

## 1. The problem in one paragraph

A car factory has many software systems, and each system gives the **same machine a different name**.

| System | Name for the *same* welding robot |
|---|---|
| SAP PM (maintenance) | `DDN1-BIW-L2-ST04-RB07`, equipment no. `10007xxx` |
| PI Historian (sensors) | `DDN1_BIW_L2_R07_WELDCUR.PV` |
| Alarm system | `BIW_L2_ST04_RB07` or `BIW.L2.ST04.RB07` |
| Engineering drawing | `RB-207` |
| MES (production) | station `B2-04` |
| Technician's work order | "R7 gun tip dressing fail", "Rob 07", "L2 ST4 robo" |

Because nothing is linked, a simple question takes a week of spreadsheet work. An example: *"Which cars were welded by robot 7 while its current was low, and did they fail inspection?"*

**Your job:** build a Python pipeline that
1. **links** all these names to one canonical asset ID (this is called **contextualization** or **entity matching**),
2. puts the result in a **knowledge graph**, with things as nodes and relationships as edges,
3. uses the graph to **find real production problems** and answer questions with AI.

The canonical ID is the SAP **functional location**, for example `DDN1-BIW-L2-ST04-RB07`.

---

## 2. Concepts you must understand (and be able to explain)

### 2.1 Manufacturing / domain
| Concept | What it means | Where it appears |
|---|---|---|
| **Shops** | Press → Body (BIW) → Paint → Final Assembly | The whole dataset |
| **ISA-95 hierarchy** | Site › Area(Shop) › Line › Work cell(Station) › Equipment › Component | `functional_location` |
| **VIN** | 17-char vehicle ID (ISO 3779) | vehicles, passages, torque, defects |
| **MES / RFID passage** | Each car is scanned at each station; this gives you *when* the car was *where* | `mes_vehicle_passages` |
| **Takt time** | 2.4 min between cars | Used to fill missing RFID reads |
| **Historian / tag** | A sensor signal stored every minute | `historian_tag_list`, `timeseries_1min` |
| **ISA-5.1 tag letters** | TT = temperature transmitter, PT = pressure, FT = flow | Drawings |
| **ISO 14224** | Standard list of equipment types and failure modes | Work-order failure codes |
| **CMMS / work order** | Maintenance tickets (CM = repair, PM = preventive, CAL = calibration) | `maintenance_work_orders` |
| **Andon** | An operator calls for help | `alarms_andon_events` |
| **Genealogy** | Which supplier lot went into which car (used for recall scope) | `part_lot_genealogy` |

### 2.2 Data / ML
| Concept | Why you need it |
|---|---|
| **Data profiling and data quality** | Part B: find typos, gaps, wrong units, duplicates |
| **Regex parsing** | Split `DDN1_BIW_L2_R07_WELDCUR.PV` into shop=BIW, line=L2, robot=07, signal=WELDCUR |
| **Blocking / candidate generation** | Don't compare 1,541 tags × 455 assets blindly; keep the top-k likely matches |
| **TF-IDF on character n-grams, rapidfuzz** | Fuzzy string similarity that survives typos |
| **Supervised classifier** (logistic regression / LightGBM) | Learns "is this (record, asset) pair a true match?" from the TRAIN labels |
| **Precision / Recall / F1, PR curve** | How good the matcher is; choose auto-accept thresholds |
| **Anomaly detection** (rolling z-score, Isolation Forest) | Part E1: find drifts, stuck sensors, spikes |

### 2.3 Graph / AI
| Concept | Why you need it |
|---|---|
| **Knowledge graph, ontology** | Defines the node types (Equipment, Vehicle…) and edge types (partOf, passedThrough…) |
| **Property graph (Neo4j, Cypher)** vs **RDF (SPARQL)** | You must pick one and justify the choice |
| **Provenance** | Every edge stores *source, method, confidence, timestamp*, so you can always answer "why does the graph think this?" |
| **GraphRAG** | An LLM writes a Cypher query, runs it read-only, and answers *only* from the results, with citations |

### 2.4 Vendor platforms (Part A research)
- **Cognite Data Fusion (CDF):** assets, time series, events, files; Data Modeling Service with **containers** (storage) and **views** (how users see data); the Core Data Model; entity matching; diagram parsing; Atlas AI.
- **Siemens:** Insights Hub asset model, Industrial Knowledge Graph, Asset Administration Shell (AAS), Industrial Copilot.
- **A third platform:** AWS IoT TwinMaker, Azure Digital Twins, or AVEVA PI AF.

---

## 3. Problems already spotted in the data (Part B preview)

From a first look at `quality_defects.csv` per day and the time-series statistics. We will prove each one properly later.

| # | Dates | Symptom | Suspected cause (to verify) |
|---|---|---|---|
| 1 | 3 Sep | Panel split / crack / neck-split spike | Press line problem (die change? tonnage) |
| 2 | 3–4 Sep | "Wheel nut torque low" spike (31 on 4 Sep) | A nutrunner out of calibration |
| 3 | 7–8 Sep | Cold weld / undersize / chisel test fail | Weld current drift on a Body robot; note the odd tag `DDN1_BIW_L1ST3_RB5_WELDCUR.PV` (relocated robot?) |
| 4 | 8–10 Sep | Water leak spike (72 on 9 Sep) | Sealer nozzle temperature low (min 24.7 °C vs nominal 45 °C) |
| 5 | 10 Sep | Craters | Booth B (TC2) humidity up to 87.9 % (limit 75 %) |
| 6 | whole period | AHU TC1 supply fan vibration rising | Bearing degradation (predictive maintenance) |
| 7 | — | Oven 2 Zone 3 max 351 °F | Spike or sensor fault? |

Some metadata is also inconsistent: oven temperatures are in °F, and stations OV-1/OV-2 are labelled area `ASSY` instead of `PAINT`.

---

## 4. Ten-day build plan

| Day | What we build | Assignment part | Output |
|---|---|---|---|
| 1 | Project setup, loaders, dataset profile | B | `reports/01_dataset_profile.md` |
| 2 | Data-quality checks, identity-scheme table, problem evidence | B | `reports/02_data_quality.md`, `03_identity_schemes.md` |
| 3 | Part A research write-up (you read vendor docs, I help structure) + ontology YAML | A, D | `docs/part_a_research.md`, `ontology/ontology_v1.yaml` |
| 4 | Tag parser + rules matcher (baseline) + evaluation | C | Rules-only F1 |
| 5 | Candidate generation (TF-IDF) + ML classifier + thresholds | C | ML F1, PR curve |
| 6 | Work orders (Hinglish, ISO 14224), alarms, documents/OCR, MES station mapping, VIN traceability | C | Linked tables |
| 7 | Review queue (Streamlit) + graph loader (Neo4j) + queries 1–7 | C, D | Graph + query outputs |
| 8 | Anomaly detection → graph events → affected VINs | E1 | Anomaly report |
| 9 | GraphRAG Q&A + 10 test questions; tests; one-command run | E2 | Q&A eval |
| 10 | Report (8–12 pages), slides, 5-min demo video | All | Final deliverables |

---

## 5. Interview preparation, starting now

The assignment says: *"AI coding assistants are allowed, but disclose where you used them and be ready to explain every line."*

- Keep a note in `docs/AI_USAGE.md` of what the AI wrote and how you checked it.
- After each step, re-run the code yourself, change one thing, and see what happens.
- Practise the 7 interview questions at the end of the assignment PDF. Each day's notes say which question that day's work answers.
