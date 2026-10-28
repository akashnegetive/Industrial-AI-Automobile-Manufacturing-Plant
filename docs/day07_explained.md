# Day 7 – Review screen, Neo4j knowledge graph, the seven queries (Part C7, Part D)

| Piece | Code | Output |
|---|---|---|
| Neo4j database | `docker-compose.yml` | Neo4j 5.26 Community on `bolt://localhost:7687`, browser on http://localhost:7474 |
| Review queue and decisions (C7) | `src/ddn/review.py` | `data/review/decisions.csv` |
| Review screen (C7) | `apps/review_app.py` (Streamlit) | – |
| Graph loader (D) | `src/ddn/graph.py` | `reports/11_graph_load.md` |
| Queries D1–D7 (D) | `src/ddn/queries.py` | `reports/12_graph_queries.md` |

The one-command run now has **14 steps**, about 5 minutes. All 56 tests pass with Neo4j running; without Neo4j the run gives 12 steps and **53 passed, 3 skipped**.

## 1. Confidence gate and review (C7)

| Band | What happens |
|---|---|
| Auto-accept (above the PR-curve threshold) | Edge goes into the graph with `status=approved` |
| Review | Shown in the review app; **not** in the graph until an engineer approves it |
| Backlog | Data-quality queue; never in the graph |

- The queue holds 175 items: 122 work orders, 44 document links (OCR labels and manual model variants) and 9 tags.
- Each decision (approve / reject / correct) is **appended** to `data/review/decisions.csv`, with a later decision overriding an earlier one. The file is kept in Git because engineer decisions are labelled data.
- **Reuse 1:** the graph loader turns approved and corrected decisions into edges with `method=engineer, confidence=1.0`.
- **Reuse 2:** the ML matcher adds them to the training labels of its *final* model. Cross-validation stays on the engineer-confirmed TRAIN labels, so reported scores aren't inflated. Cognite calls this "refit" on confirmed matches.
- **Screen:** one item at a time, with context (tag description and unit, or work-order text, date and SAP number), the proposed asset and its confidence, and Approve / Reject / "correct to" (a searchable asset list). It's tested headlessly with Streamlit's `AppTest`.

## 2. Storage choice: Neo4j property graph
- The questions are **paths with time filters** (VIN → station → equipment → signal window). A property graph keeps time, confidence and provenance on the edge itself.
- **Cypher** is what an LLM writes most reliably, which matters for Day 9.
- Values stay in **Parquet**. A `TimeSeries` node holds `store_uri` plus a cached latest value, and queries read the window from Parquet (see D2).

## 3. Graph loader (`graph.py`)

**Containers (Cognite mapping):** one uniqueness constraint per node key, all generated from the ontology YAML, plus range indexes on `passedThrough.passed_at`, `processedBy.start`, `Defect.detected_at` and `TorqueResult.timestamp`. Every asset also carries a generic `:Asset` label so edges can find it by `fl`, whatever its level.

**Provenance is enforced, not hoped for:** all edges go through `edges()`, which raises an error if any row lacks `source_system`, `method`, `confidence`, `created_at` or `status`.

**Method per link** (what D6 groups by):
| Method | Meaning |
|---|---|
| `source_key` | Direct key from a source system (MES passage, torque result, SAP parent) |
| `rule` | Rules matcher agreed, or a deterministic rule (alarm path, document label) |
| `ml` | Only the ML matcher found it (152 edges) |
| `derived` | Computed from other facts (processedBy from passage + station equipment) |
| `inferred` | Missed RFID read filled from line order |
| `engineer` | Review decision |

**Relocated robot:** `DDN1-BIW-L2-ST06-RB12` has **two** `partOf` edges, to L1-ST03 with `valid_to = 2026-03-01` and to L2-ST06 with `valid_from = 2026-03-01`. Queries only follow current edges (`valid_to IS NULL`), and processedBy only links cars built after the move.

**Result:** 165,698 nodes and 1,133,743 relationships in about 3.5 min. After loading, the checks are: 0 edges without provenance, 0 edges whose endpoints break the ontology, and 0 provenance values outside the ontology's allowed lists.

**What the checks caught:** two ontology mistakes, so the ontology is now **v1.1.0** with a changelog. Sealer dispensers (Components) process cars, and tool channels are `partOf` a controller Component. Seven MES stations are line-level in SAP, so `passedThrough` may also end at a `Line`. The loader's own "method" values for documents were also outside the allowed list and are fixed.

**Speed:** about 70% of the first 6.5-minute load was Python converting 11 million values one by one. A vectorised conversion took the Python share down to under 2 minutes. Clearing the old graph is done in batches (relationships first) to stay inside Neo4j's transaction memory.

## 4. The seven queries (`queries.py`)
| # | View | Answer (this data) |
|---|---|---|
| D1 | Maintenance | 4 temperature sensors in Oven 2 (deg F in WinCC, stored as deg C); no open work orders, because every WO in the export is closed |
| D2 | Quality | Demo VIN `…4375`: the SR03 pass is *inferred* (reader offline); SR03 nozzle at 38–39 °C while sealing it |
| D3 | Traceability | 37+ VINs, all on TC14 → NR14. **NR14 has no calibration WO in 12 months** (D3b: only 2 of 20 nutrunners) |
| D4 | Quality | Crater spike 10 Sep 16:00 → upstream ranking puts **AHU-TC2** first (184 alarms, 90 min RH > 75 %) |
| D5 | Traceability | Lot scope 1,785 cars; evidence-based scope 1,492 (the 4 Sep session had 0 leaks) |
| D6 | Maintenance | 9 tags and 122 WOs unlinked (= review band); below 0.8: only 271 inferred after-buffer passages |
| D7 | Plant head | Cars exposed to each known problem vs caught by inspection, e.g. door-seal lot: 1,492 at risk, 85 caught |

**Two findings that came from the graph itself:**
- **Calibration gap (D3/D3b):** only NR04 and NR14 lack a calibration in 12 months, and NR14 is the tool that drifted. The `T-40 Calibration due` alarm fires on every nutrunner, so it gives no warning.
- **The review loop:** the repair WO for NR14 (4102964) isn't in the graph because it's in the review band. Approving it in the review app makes it appear in D3. That's a good live demo.

## 5. Scale
1.1 M edges for 7,200 cars. The assignment's 18,000 cars × 40 stations would be about 2.8 M. That stays fast because VINs link to 51 stations, not to every machine; `processedBy` is only for equipment that touches the car; time filters use range indexes; and values never enter the graph. At 10 plants, you'd use one database per plant (or a site key on every node) and bulk-import with `neo4j-admin`.

## Exercises
- Open http://localhost:7474 (user `neo4j`, password `ddn-plant-2026`) and run: `MATCH p=(:Vehicle {vin:'MDDA5XK0XD004375'})-[:passedThrough]->(s) RETURN p LIMIT 50`
- In the review app, approve WO 4102964, run `run_all` again, and check D3 in `reports/12_graph_queries.md`.
- Change D5's lot to another door-seal lot and compare leak counts.
