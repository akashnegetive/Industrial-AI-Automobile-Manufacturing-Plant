---
title: "Day 3 to Day 10 explained – Plant DDN-01"
---

# Day 3 to Day 10, explained simply

**How to use this guide.** Each day has the same five parts:

- **Goal**: what we wanted to achieve that day, in one line.
- **What we did**: the steps, with a real example from the data.
- **Why**: the reason behind each choice (this is what interviewers ask).
- **Result**: the numbers to remember.
- **Say it in the interview**: a short answer you can speak.

At the end there are the **top 50 interview questions with answers**.

<div class="note"><b>Quick recap of Day 1–2 (before this guide starts).</b> Day 1: set up the project, read the data pack (9 files for plant DDN-01, 1–14 Sep 2026). Day 2: <b>Part B</b>: profiled every file, found <b>38 data-quality issues</b> (°F values, duplicates, missing parent assets, clock problems), described <b>9 identity schemes</b> (how each system names a robot) and found the <b>9 production problems</b> hidden in the data (bad welds, sealer leaks, a bad door-seal lot…). Days 3–10 build everything on top of this.</div>

## The whole journey in one table

| Day | Theme | Assignment part | Main output |
|---|---|---|---|
| 3 | Vendor research + design the ontology | A, D (design) | `part_a_research.md`, `ontology_v1.yaml` |
| 4 | Clean the data + rules-only matcher | C1, C8 | staging Parquet, rules baseline |
| 5 | Machine-learning matcher | C2, C3, C7, C8 | LightGBM links with confidence |
| 6 | Documents, work orders, stations, VIN trace | C4, C5, C6 | OCR links, failure modes, car paths |
| 7 | Review screen + Neo4j graph + 7 queries | C7, D | the knowledge graph |
| 8 | Anomaly detection with context | E1 | 8 anomaly events judged |
| 9 | GraphRAG (ask questions in English) | E2 | cited answers from the graph |
| 10 | Deliverables + three-band gate + link prediction | C, E3 | predictions, report, slides, video |

A simple way to remember it: **Design (3) → Clean (4) → Link (5, 6) → Store (7) → Detect (8) → Ask (9) → Ship (10).**

# Day 3 – Vendor research (Part A) and ontology design

**Goal:** learn how big platforms solve this problem, then design our own data model (the ontology) before writing any loader.

## 3.1 Part A: research on three platforms

We compared **Cognite Data Fusion**, **Siemens** (Insights Hub, Industrial Information Hub, Industrial Copilot) and **AWS IoT TwinMaker** on the same rows: how they model assets, how they link data, how they show confidence, which standards they support, what GenAI they offer, and where they keep sensor values.

**Why AWS as the third one?** It has a real knowledge graph with a query language (PartiQL `MATCH`) and a published automotive story (Volkswagen's Digital Production Platform).

**Ideas we borrowed (say these!):**

| From | Idea | Where it is in our project |
|---|---|---|
| Cognite | Links have a status: *suggested / approved / rejected* | `status` on every edge |
| Cognite | Rules and confirmed matches go first, then the model, then a threshold | rules → LightGBM → gate |
| Cognite | Values stay outside the graph; the graph holds a pointer | `TimeSeries.store_uri` → Parquet |
| Cognite | "Containers" (storage) vs "views" (what a role sees) | Neo4j labels + 3 views |
| AWS / Cognite | Asset hierarchy as parent–child | `partOf` edges |

**Honesty rule:** every one of the 35 links was opened and checked (`docs/part_a_link_check.md`). Claims with no official source are marked ⚠ "not found" instead of guessed. Example: we could not find any named car maker in a Cognite case study, so we wrote that.

## 3.2 What is an ontology? (simple words)

An ontology is the **list of things and allowed connections** in our world. Like a grammar for the graph.

- **Things (node types):** Site, Shop, Line, Station, Equipment, Component, Tool, TimeSeries, WorkOrder, FailureMode, Document, Alarm, AnomalyEvent, Vehicle, Part, SupplierLot, TorqueResult, Defect (18 in the final version).
- **Connections (edge types):** e.g. `Equipment –partOf→ Station`, `Vehicle –passedThrough→ Station`, `Defect –causedBy→ AnomalyEvent` (19 in the final version).
- Each edge says **from which type to which type** it can go. `Vehicle –partOf→ Station` is not allowed.

**Example in plain words:** "Robot RB07 is part of Station 04. Car MDDA…3924 passed through Station 04 at 10:15. Its defect D700356 was caused by anomaly AN-003 on RB07."

## 3.3 Why we wrote it as a YAML file + validator

The ontology is a **contract**. Three later pieces depend on it:

1. the **graph loader** (creates exactly these labels and constraints),
2. the **validation** after loading (no edge may break the rules),
3. the **GraphRAG prompt** (the LLM is told exactly this schema).

If each had its own copy, they would drift apart. So there is **one file**, `ontology/ontology_v1.yaml`, and `src/ddn/ontology.py`:

- parses it into **pydantic** models, so a typo like `strng` instead of `string` fails loudly;
- checks every edge points to a real node type, every key is required, the provenance fields exist;
- writes `docs/ontology.md` with a diagram.

**Try it:** change `to: [Station]` to `to: [Stattion]` and run `make ontology`. You get a clear error.

## 3.4 Key design choices from this plant's data

| Choice | Why (real example) |
|---|---|
| `partOf` is **time-valid** (`valid_from`, `valid_to`) | Robot **RB12 moved** from L1-ST03 to L2-ST06 in March 2026. A car built before the move must link to the old place |
| Station has `mes_code` | MES calls it `B2-04`, SAP calls it `DDN1-BIW-L2-ST04`. Same place, one node, two names |
| Equipment keeps `aliases` | The same robot is `R07`, `RB-207`, `BIW/L2/S4/RB07` in different systems |
| `passedThrough.inferred` | RFID reader at SLR-2 was offline; guessed passages must be marked |
| `causedBy` is never `source_key` | No system records causes. Causes are always *derived* or *engineer*-approved |
| Provenance on **every** edge | `source_system`, `method`, `confidence`, `created_at`, `status` are required |

## 3.5 Why a property graph (Neo4j) and not RDF

- Our questions are **paths with time filters**: car → station → robot → signal in a time window.
- A property graph keeps **time, confidence and provenance on the edge** itself. In RDF you need extra tricks (reification / RDF-star).
- LLMs write **Cypher** well, which matters for GraphRAG on Day 9.
- Trade-off: no built-in OWL reasoning. We could export to RDF later if a customer needs AAS/RDF.

**Result of Day 3:** research draft + ontology v1.0 + validator + tests.

<div class="say">"Before writing any loader, I designed the ontology as one versioned YAML file. The loader, the validation and the GraphRAG prompt are all generated from it, so they can never disagree. Design choices came from the data: for example, a robot moved lines in March, so the partOf edge is time-valid."</div>

# Day 4 – Staging, tag parser and the rules-only baseline

**Goal:** clean all raw data into tidy tables, then build the **simplest possible matcher (rules)** so we have a baseline that ML must beat.

## 4.1 Staging (`src/ddn/tags.py`) – Part C1

Raw data is messy. Staging makes it clean and typed.

**1. Parse every tag name.** The historian tags come from 4 systems with different naming styles (PI, WinCC, S7, MES). One regex per system splits a tag into parts.

| Raw tag | Parsed |
|---|---|
| `DDN1_BIW_L2_R07_WELDCUR.PV` (PI) | shop BIW, line L2, equipment R07 → RB07, signal WELDCUR |
| `PaintShop-Ovn02-Z3FAN-Spd` (WinCC) | shop PNT, area OV2, equipment Z3 FAN, signal speed |

**2. Validate** each parsed tag with a pydantic `TagRecord`, so wrong types fail at load time.

**3. Add an ISA-5.1 code** (the instrument standard): TEMP → `TT` (temperature transmitter), PRESS → `PT`, VIB → `VT`, RH → `MT`.

**4. Fix units.** Some oven temperatures were in **°F**. We converted to °C. Check: Oven 2 zone 3 now has median **149.8 °C** against a set point of 150 °C. That proves the conversion is right.

**5. Repair missing parents.** 18 assets had a parent that did not exist. We walk up the functional location path until we find an existing asset. Example: if `DDN1-BIW-L2-ST09` is missing, the child hangs from `DDN1-BIW-L2`.

**6. Store values as Parquet, partitioned by tag.** 1.1 million sensor values. The graph will only store the pointer.

**Bug found and fixed (good interview story):** writing a partitioned Parquet folder a second time **adds** files instead of replacing them, so values got duplicated on re-run. Fix: delete the folder first and check row counts: **1,101,823 in = 1,101,823 out**. This makes the step **idempotent** (run it twice, same result).

**Normalize, but don't fix typos.** Documented variants (Oven2 / OVN2 / Ovn02) are normalized. Real typos (`BWI` instead of `BIW`, `DN1_`) are left alone on purpose: fixing those is the ML matcher's job, and the gap shows how much ML helps.

## 4.2 Rules matcher for tags (`match_rules.py`)

**The suffix index trick.** For every asset, store every ending of its path below the line:

```
DDN1-BIW-L2-ST04-RB07  →  (BIW, L2, "ST04RB07"), (BIW, L2, "RB07")
DDN1-PNT-OV2-Z3-FAN    →  (PNT, OV2, "Z3FAN"),   (PNT, OV2, "FAN")  ← "FAN" ambiguous → removed
```

If a key points to **more than one** asset, it is deleted. So the rules link only when the answer is **unique**. That is why rules precision is 1.000: they never guess.

| Rule | When it fires | Confidence |
|---|---|---:|
| exact | tag follows its documented naming | 0.99 |
| alias | same, after normalizing a WinCC area name | 0.97 |
| relocation | old name + an asset description says "Relocated from L1 ST03 (ex R05)" | 0.95 |

The relocation rule **reads the asset description**, it is not hard-coded. If another robot moves, it still works.

**Zero-padding bug:** SAP has `AGV07` (padded) and `P1` (not padded). The first version always padded and broke 4 pump tags. Now it tries "as written" then "padded".

## 4.3 Rules matcher for work orders

Uses only structured fields, in order of trust: FL text that is a path fragment (0.97) → FL text equal to a **unique** asset name (0.90) → SAP equipment number (0.85). "Robot 07" exists on 3 lines, so it is never used alone.

**Key finding:** all **20 wrong links** came from the **SAP equipment number**. Lesson: *a key from a source system is not always the truth.* The ML model must check the number against the text.

## 4.4 How we measure (`evaluate.py`) – Part C8

```
precision = correct links / all links we made      ("when we link, are we right?")
recall    = correct links / all true links          ("how many did we find?")
F1        = 2 × P × R / (P + R)                     (one number for both)
```

A **wrong** link counts twice: as a false positive (bad edge) **and** a false negative (right edge missing). Why: in a recall investigation, a wrong edge sends people to the wrong robot, which is worse than a missing edge.

## 4.5 Result of Day 4

| Source | Precision | Recall | F1 | Wrong links |
|---|---:|---:|---:|---:|
| Tags (539 labels) | 1.000 | 0.974 | 0.987 | 0 |
| Work orders (888 labels) | 0.976 | 0.925 | 0.950 | **20** |

**What Day 5 must beat:** 14 typo tags (with zero wrong links), 47 work orders with only free text, and the 20 wrong SAP numbers.

<div class="say">"I always build a rules baseline first. It tells me how hard the problem really is and gives ML a number to beat. Rules got tags almost perfect, but on work orders they made 20 wrong links, all from a wrong SAP equipment number. That told me the ML model needed a feature that checks the number against the text."</div>

# Day 5 – The machine-learning matcher

**Goal:** link the hard records (typos, free text, wrong SAP numbers) with ML, and give **every link a trustworthy confidence score**.

## 5.1 Step 1 – Text normalization (`textnorm.py`)

The same token extractor runs on asset names, tag names and work-order text, so we compare like with like.

| Messy text | Tokens |
|---|---|
| `R7 gun tip dressing fail` | `RB07 WG` (WG = weld gun) |
| `Rob 12 ka gun nahi chal raha` (Hinglish) | `RB12 WG` + "not running" |
| `DC tool 14` / `Nutrunner 14` / `NR14` | `NR14` |
| `Sealer robo 3` | `SR03` (not RB03!) |

**Order matters:** "Sealer robo" must be handled **before** "robo → robot", or a sealer becomes a welding robot. A test protects this.

## 5.2 Step 2 – Blocking (candidate generation) – Part C2

Comparing every record with all **455 assets** is slow and gives the model mostly silly pairs. So each record gets a short list (about **20 candidates**) from:

1. **top 15** assets by character n-gram **TF-IDF** (2–4 letters, so `BWI` still looks like `BIW`);
2. every asset whose equipment code is in the text ("R7" with no line → robot 7 on L1, L2 **and** L3);
3. the rules answer and the SAP-number answer;
4. parents and children (robot ↔ its weld gun).

**Blocking recall** = is the true asset in the short list? Tags **1.000**, work orders **0.999**. This is reported separately because if the true asset is not in the list, no model can ever find it.

## 5.3 Step 3 – Pair features – Part C3

For each pair (record, candidate) we ask: *does this candidate agree with what the record says?* The list has 24 features; 23 are active (the sentence-embedding one is off because Hugging Face was blocked).

| Group | Examples |
|---|---|
| String similarity | TF-IDF score, fuzzy match to name, fuzzy match to FL |
| Token agree / conflict | same line? different line? same station? same equipment code? |
| Domain knowledge | `unit_compat`: kA fits a robot, Nm fits a nutrunner, %RH fits an air handler |
| Other sources | did the rules agree? does the SAP number point here? |
| **Trust in SAP number** | `eqno_text_agree`: does the text confirm the SAP number? |
| Ambiguity | how many candidates share this equipment code (robot 7 on 3 lines) |
| Time | `valid_at_time`: was this asset at this place at the record's date? (RB12 move) |

**Example:** WO text "Nutrunner 01 annual calibration", SAP number points to NR03. `equip_match` for NR01 = 1, `eqno_text_agree` for NR03 = 0. The model learns: *when text and number disagree, trust the text*.

## 5.4 Step 4 – LightGBM model and honest evaluation

- **LightGBM** = gradient-boosted decision trees. Good for tabular features, learns combinations like "SAP number present **but** text contradicts it" by itself, trains in seconds, explainable.
- Settings: 300 trees, learning rate 0.05, 15 leaves.
- **GroupKFold (5 folds), grouped by record:** all candidates of one work order stay in the same fold. So the model is never tested on a record it saw in training. Every number we report is **out-of-fold** (honest).
- The record's answer = the candidate with the highest probability; that probability = **confidence**.

## 5.5 Step 5 – Thresholds from data – Part C7

We do not pick 0.5 by habit. We look at the out-of-fold results sorted by confidence:

| Band | Rule | Work-order threshold |
|---|---|---|
| **Auto-accept** | precision ≥ **0.995** above it **and** no "wrong-machine" error above it | ≥ **0.932** |
| **Review** | between auto and backlog | between |
| **Backlog** | below the score where the top candidate was right ≤ 25 % of the time (final, Day 10) | < **0.093** |

**Two kinds of error:** a *near-miss* (right machine, wrong level: robot vs its own weld gun) and a *wrong-machine* error (a different robot or line). Wrong-machine errors are **never** allowed in auto-accept.

**Trade-off example from the report:** at 0.50 there were 4 wrong auto-links (3 wrong machines); at 0.932 there are **0**, and only 12 more records go to review. A review costs an engineer one minute; a wrong link can send a recall investigation to the wrong robot.

## 5.6 Result of Day 5 (after Day 6 bug fixes)

| Source | Rules F1 | **ML F1** | Wrong auto-links |
|---|---:|---:|---:|
| Tags | 0.987 | **1.000** | 0 |
| Work orders | 0.950 | **0.982** | **0** (rules had 20) |

1,532 of 1,541 tags (99.4 %) and 2,846 of 2,968 work orders (95.9 %) are linked automatically.

**What is still wrong (all in review, not in the graph):** "R7 dress pack…" (robot 7 exists on 3 lines, no line given), "WG water leak at cap adaptor" (no equipment at all). Only a person can decide these.

<div class="say">"The ML matcher works in three stages: blocking gives about 20 candidates, 23 features describe how well each candidate agrees with the record, and LightGBM scores them. I evaluate with GroupKFold so scores are out-of-fold, and I choose the auto-accept threshold where precision is at least 99.5 % with zero wrong-machine errors. Result: work-order F1 went from 0.950 to 0.982, and wrong automatic links went from 20 to zero."</div>

# Day 6 – Documents, work orders, stations, alarms and VIN traceability

**Goal:** link everything that is *not* a tag: drawings, manuals, the meaning of work orders, MES stations, alarms, and the path of every car.

## 6.1 Documents and OCR (`documents.py`) – Part C5

**Drawings (7 PDFs):**

1. **PyMuPDF** reads the text layer. A page with **no text layer is a scan**, so we render it at 300 and 400 dpi and read it with **Tesseract OCR** in two modes (block mode for big labels, sparse mode for small ones), then merge.
2. The **drawing number gives context**: `DWG-BIW-L2-001` means shop BIW, line L2.
3. A label table turns local labels into asset keys: `RB-207` → `RB07`, `TD-2.04` → station 04 tip dresser, `AHU-02` → `AHUTC2`.
4. Keys go through the **same asset index as the tag matcher** (one source of truth).
5. Each hit becomes a `mentionedIn` edge with **page, label, method, confidence**.

| How the label was read | Confidence | Band |
|---|---:|---|
| Text layer | 0.95 | auto-accept |
| OCR, exact | 0.85 | review |
| OCR after correction (`LUB-12` → `LUB-1.2`) | 0.70 | review |

**Result:** 145 labels on 7 drawings resolved. The scanned drawing has 18 labels (counted by eye); OCR found **15**. The 3 missing are listed, not guessed.

**Manuals** link to equipment by **model** (e.g. robot model OR-210). From the manuals we extracted **16 alarm codes** with causes, and **14 ISO 14224 failure modes**.

**If Tesseract is not installed** (fresh Windows laptop), the scan is skipped with a message and everything else still runs.

## 6.2 Work orders: what failed? (`workorders.py`) – Part C4

Maintenance writes free text like *"Rob 12 ka gun nahi chal raha, servo reset kiya"*. We want a standard **ISO 14224 failure mode**.

- We use **spaCy** (blank English model + **EntityRuler**, a rule-based entity finder). No model download, works offline, and every result can be traced to a rule.
- Entities: `FAILURE` (with ISO code), `ACTIVITY` (routine work like PM), `EQUIPMENT` (R7, DC tool 14).
- **Hinglish first:** "trip ho raha hai" → "tripping" → `UST` (spurious stop); "nahi chal raha" → "not running" → `FTS` (fail to start).

| Text | Failure mode |
|---|---|
| "oven zone not heating" | `LOO` (low output) |
| "valve stuck open" | `FTC` (fail to close) |
| "TT-301 reading frozen" | `AIR` (abnormal instrument reading) |
| "fan bearing noise" | `VIB` (vibration) |

**Result:** 100 % of corrective WOs get a failure mode; all 8 root-cause WOs get the right one.

**Finding:** SAP's own `failure_code` field does **not** match the text ("water leak" WOs are coded LEAK only 20 % of the time, about chance). So we never use it as a label, and it became data-quality issue #38.

## 6.3 Stations, process flow and alarms (`context.py`)

- **MES station → SAP functional location:** all 46 stations mapped (`B2-04` → `DDN1-BIW-L2-ST04`).
- **51 `feeds` edges:** the car's route in order, each air handler → the paint booth it conditions, each press line → the body station where its panels are fitted.
- **Alarms:** separators normalized (`BIW/L2/S4/RB07` → `DDN1-BIW-L2-ST04-RB07`). 100 % linked, 231 duplicates **flagged** (not deleted), 59 % explained by a manual's alarm code.

## 6.4 VIN traceability (`trace.py`) – Part C6

**Problem:** the RFID reader at SLR-2 was offline, so some cars have no read there.

**Solution – fill the gap with the car's own delay.** Compare the car with the normal schedule. If it was 3 minutes late at SLR-1 and 5 minutes late at SLR-3, it was about **4 minutes late at SLR-2**. Filled passages get `inferred = true`.

**We tested the guess:** hid 2 % of **real** reads and re-estimated them. Median error **0.28 min**; 95.7 % within one takt (2.4 min). Errors are big only after **buffers** (cars wait there for unknown time, ~25 min). So each inferred passage stores `uncertainty_min`, and confidence is 0.85 (normal) or 0.60 (after a buffer).

**processedBy (511,182 edges):** which machine worked on which car. Robots and sealers are **derived** from station + time. Nutrunners are **observed** from torque results. The moved robot RB12 only links to cars built after the move.

**Demo car:** `MDDA5XK0XD004375`. SLR-2 passage inferred (reader offline). Sealer SR03 nozzle was at **38–39 °C** (set point 45 °C) while sealing it. Defect: **water leak at the roof ditch**. One car, four systems, one story.

## 6.5 Bugs found on Day 6 (great interview stories)

| Bug | Effect | Fix |
|---|---|---|
| `TT-301` not recognized | WO "TT-301 reading frozen" linked to the wrong unit (UF-301) | ISA-5.1 instrument tags map to their loop's vessel |
| pandas 3 stores missing text as `NaN`; `x is not None` is True for NaN | several conflict features were wrong | `has()` helper |
| Matcher had no idea of time | "R12…" before March linked to L2's robot 12 | `valid_at_time` feature |
| Threshold ignored error type | a different-robot error could be auto-accepted | auto-accept needs zero wrong-machine errors |

After fixes: WO F1 0.982, auto threshold 0.932, 0 wrong auto-links.

<div class="say">"For missed RFID reads, I don't just copy the average time. I interpolate each car's own delay between its real reads, and I validated it by hiding 2 % of real reads: median error 0.28 minutes. Where the error is large, after buffers, the edge gets a lower confidence and an uncertainty in minutes, so nobody mistakes a guess for a fact."</div>

# Day 7 – Review screen, Neo4j knowledge graph, the seven queries

**Goal:** let engineers decide unsure links, load everything into **Neo4j** with provenance, and answer the assignment's **7 questions (D1–D7)**.

## 7.1 Confidence gate and review screen – Part C7

| Band | What happens |
|---|---|
| Auto-accept | edge goes into the graph, `status = approved` |
| Review | shown in the Streamlit review app; **not** in the graph until approved |
| Backlog | data-quality queue (on Day 10 these get link-prediction suggestions) |

- The review screen shows **one item at a time** with context (tag description and unit, or WO text, date, SAP number), the proposed asset and confidence, and buttons **Approve / Reject / Correct to…** (searchable asset list).
- Each decision is **appended** to `data/review/decisions.csv` (kept in Git, because these are valuable labels).
- **Reuse 1:** the loader turns approved/corrected decisions into edges with `method = engineer`, confidence 1.0.
- **Reuse 2:** they are added to the **training labels** of the final ML model (Cognite calls this "refit"). Cross-validation still uses only TRAIN labels, so scores are not inflated.
- Quick path: `python -m ddn.graph --decisions` writes decisions into the running graph in seconds.

## 7.2 The graph loader (`graph.py`)

- Runs Neo4j 5.26 Community in **Docker**.
- Creates a **uniqueness constraint** per node key (generated from the ontology), plus range indexes on time properties (`passed_at`, `start`, `detected_at`).
- Every asset also gets a generic `:Asset` label so edges can find it by `fl` at any level.
- Loads in batches: `UNWIND $rows AS r MERGE (n:Label {key: r.key}) SET n += r`. `MERGE` = "create if missing, else update", so **re-loading never duplicates**.
- **Provenance is enforced in code:** all edges go through one function that raises an error if any row is missing `source_system`, `method`, `confidence`, `created_at` or `status`.

**Methods on edges:**

| Method | Meaning | Example |
|---|---|---|
| `source_key` | a direct key from a source system | MES passage, SAP parent |
| `rule` | a rule matched | alarm path, document label |
| `ml` | only the ML matcher found it | odd work-order text |
| `derived` | computed from other facts | processedBy from passage + station |
| `inferred` | gap filled | missed RFID read |
| `engineer` | review decision | approved in the screen |

**After loading, three checks:** 0 edges without provenance, 0 edges whose endpoints break the ontology, 0 provenance values outside the allowed lists. These checks **caught two ontology mistakes** (e.g. sealer dispensers are Components and they process cars), so the ontology went to v1.1 with a changelog. *This is why validation matters.*

**Speed fix:** the first load took 6.5 min; 70 % was Python converting 11 million values one by one. Vectorized conversion brought it down a lot.

## 7.3 The seven queries (D1–D7)

| # | Question (simple) | Answer from our graph |
|---|---|---|
| D1 | What sensors does Oven 2 have, and open work orders? | 4 temperature sensors (°F in WinCC, stored as °C); no open WOs (export has only closed ones) |
| D2 | For a water-leak car, which sealer robot, and what was its nozzle temperature? | Car …4375: SR03 pass was *inferred*; nozzle 38–39 °C while sealing it |
| D3 | Cars with low wheel-nut torque: which tool? Was it calibrated? | All on TC14 → **NR14**. NR14 had **no calibration WO in 12 months** |
| D4 | Paint craters spiked on 10 Sep 16:00. What upstream caused it? | **AHU-TC2** first (184 alarms, 90 min humidity > 75 %) |
| D5 | Which cars have parts from the bad door-seal lot? | 1,785 cars in the lot; evidence-based scope 1,492 |
| D6 | What is not linked or low confidence? | 9 tags + WOs in review; 271 inferred after-buffer passages below 0.8 |
| D7 | (plant head) Cars exposed to each problem vs caught by inspection | door-seal lot: 1,492 at risk, 85 caught |

**Two findings that came from the graph itself:**

- **Calibration gap:** only NR04 and NR14 lacked a calibration in 12 months, and NR14 is the tool that drifted. The "calibration due" alarm fires on every nutrunner, so it warned nobody.
- **The review loop as a demo:** the repair WO for NR14 (4102964) was in the review band, so not in the graph. Approve it on the screen, re-run, and it appears in D3.

**Final graph size:** 165,706 nodes and 1,137,011 relationships.

<div class="say">"The loader is generated from the ontology and uses MERGE in batches, so it is idempotent. Provenance is enforced in code: an edge without it raises an error. After loading I check that no edge breaks the ontology. Those checks actually caught two mistakes in my own ontology, which is exactly why I built them."</div>

# Day 8 – Anomaly detection linked to context (Part E1)

**Goal:** find abnormal behavior in sensor signals and, more importantly, **explain each one with the graph**: which machine, which cars, which defects, which work order.

## 8.1 The detector: robust rolling z-score

For each signal:

1. Keep only **production minutes** and **running values** (above 20 % of typical). Weld current drops to 0 between cycles; those zeros would hide a drift.
2. **Baseline** = rolling 3-day **median**. **Spread** = rolling 3-day **MAD** (median absolute deviation). Why median/MAD and not mean/std? A few outliers barely move a median, but they pull a mean a lot.
3. **Lag the baseline** so the problem does not become its own "normal": **fast lag 12 h** for sudden events, **slow lag 1 day** for slow wear (a fan bearing that worsens over 4 days).
4. `z = (value − baseline) / (1.4826 × MAD)`, smoothed over 10 minutes.
5. **Hysteresis** (like real alarm systems): an event **starts** at |z| > 6 and **continues** while |z| > 3; at least 10 minutes above 6; gaps under 60 min are merged. Without it, one fan problem showed as 10 alarms.

**Flat-line rule:** same value for ≥ 60 minutes while producing = **stuck sensor**.

**Torque:** the same z-score per tool, in 10-minute bins. Bug found: the smoothing asked for 5 points in a 10-minute window on 10-minute data, which never happens, so everything was empty. *Lesson: the window must fit the data resolution.*

**Simple example (made-up numbers to show the maths):** weld current normally 9.0 kA, MAD 0.05. It drops to 8.6 kA. z = (8.6 − 9.0) / (1.4826 × 0.05) ≈ −5.4. When it goes below about 8.55 kA (|z| > 6) for 10+ minutes, an event starts.

## 8.2 Why Isolation Forest is only the comparison

| | Z-score | Isolation Forest |
|---|---|---|
| Known problems found | **8 / 8** | 6, in short pieces |
| Stuck sensor | found | missed (a constant looks "normal") |
| Extra alerts with no cause | **0** | 6 |
| Can I explain it? | "9 spreads above its own normal" | "isolated quickly in random trees" |

Isolation Forest's `contamination` setting forces it to flag a share of **every** signal, so it always finds "something".

## 8.3 Linking each anomaly to context (where the graph helps)

For each event: **tag → equipment** → **which cars were exposed**, depending on what the machine does:

- touches the car (robot, sealer, nutrunner): the `processedBy` edges in the window;
- conditions a booth (air handler): cars that passed that booth (`feeds`);
- oven / e-coat: cars that passed the station in the window;
- press: panels pressed in the window, which are fitted about a day later.

Then **defect lift** = how much more often exposed cars got a defect than other cars. And a **confirming work order** on that equipment from 1 day before to 3 days after, preferring one whose failure mode fits (low reading → LOO, flat → AIR).

## 8.4 Judging each event (rules written down)

1. Flat line → **sensor fault**.
2. Exposed cars have a defect at **≥ 5×** the normal rate with **≥ 3 cases** → **real, quality problem**.
3. Oven over-temperature under 2 h and under +30 °C → **false alarm** (inside the burner manual's bake window).
4. No quality impact but a maintenance WO confirms it → **real, equipment problem**.
5. Nothing confirms it → **false alarm**.

## 8.5 Result

| ID | Equipment | Verdict | Evidence |
|---|---|---|---|
| AN-001 | Press PL1-PR1 | quality | all 28 panel cracks; WO 4102965 |
| AN-002 | Nutrunner NR14 | quality | all 38 loose-wheel-nut defects; flagged **5½ h before** the first NOK |
| AN-003 | Robot L2-RB07 | quality | small welds at 254× normal; WO 4102961 |
| AN-004 | Sealer SR03 | quality | roof leaks at 2,364×; WO 4102962 |
| AN-005 | AHU-TC1 fan | equipment only | bearing replaced, no defects |
| AN-006 | AHU-TC2 | quality | all 7 craters; WO 4102963 |
| AN-007 | E-coat TT-301 | **sensor fault** | flat line while producing |
| AN-008 | Oven 2 zone 3 | **false alarm** | short, small, inside bake window |

**8 / 8 found, no hand-set limits per signal, no spurious alerts.** The door-seal lot problem is invisible in signals; the genealogy query (D5) finds it.

**Into the graph (ontology v1.2):** `AnomalyEvent` nodes; `hasEvent` (equipment → event); `exposedTo` (vehicle → event, **2,956**); `causedBy` (defect → event, `method = derived`).

**Finding:** 4 of the 8 work orders that explain incidents were still **in review** (long text, no SAP number → medium confidence). So the review screen now shows **anomaly-explaining work orders first**.

<div class="say">"Detecting a spike is easy. The value is in the context. Each anomaly is linked through the graph to the machine, the cars that machine touched in that window, their defect rate compared with other cars, and a confirming work order. Then a written rule gives a verdict. I found all 8 seeded problems, and one deviation was correctly judged a false alarm because the burner manual says it's inside the bake window."</div>

# Day 9 – GraphRAG: questions in English, answers from the graph (Part E2)

**Goal:** an engineer types a question in plain English and gets an answer **from the graph**, with **citations** they can check.

**Example:** *"Why did water-leak defects rise on Line 2 last Tuesday?"* → *"15 WL-104 leaks at the front door LH upper on 08 Sep were on cars with door-seal lot WS-260904-B. [WS-260904-B, D700249, …]"*

## 9.1 The flow

1. The **LLM** (OpenAI gpt-4o, temperature 0, structured JSON) gets the question + the schema from the ontology + real values + 6 worked examples, and returns `{can_answer, reason, cypher}`.
2. **validate()** checks the Cypher (see below). Rejected → retry with the error message (up to 3 attempts).
3. Run in a **read-only transaction**, 10-second timeout, `LIMIT 100`.
4. **Evidence expansion:** fixed (not LLM-written) queries add the asset and work order of any anomaly in the rows, and root-cause facts of any lot.
5. The LLM writes the answer **only from the rows**, as sentences with citations.
6. **ground():** any sentence whose citations are not in the rows is **dropped**.
7. Three ways to say **"I don't know"**: the model says the schema can't answer, 0 rows, or nothing survives grounding.

## 9.2 Why GraphRAG and not a vector store

Our questions are about **relationships and counts**: which cars passed which robot, which lot, how many defects. A vector search finds *similar text*; it cannot count 1,785 cars or follow car → part → lot → defect. The graph already has these links with provenance, so the LLM only translates the question into a query. **Facts come from the database, not from the model's memory.**

## 9.3 Safety is in code, not just in the prompt

| Check | Stops |
|---|---|
| Forbidden words: CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD, CALL, FOREACH… | writes, procedures, file access |
| Only one statement | `MATCH … ; MATCH (n) DELETE n` |
| Every label, relationship and property must be in the ontology | invented schema like `:ShiftSupervisor` |
| Relationship direction must match the ontology | `(Defect)<-[:causedBy]-(Equipment)` |
| `EXPLAIN` first | syntax errors |
| `LIMIT 100` added | huge results |
| `execute_read` + timeout | even if something passes, Neo4j refuses writes |

## 9.4 How the score improved (the honest story)

| Run | Change | Score |
|---|---|---:|
| 1 | gpt-4o-mini, schema-only prompt | 2/10 |
| 2 | gpt-4o, real patterns, examples, direction check, retry on 0 rows | 7/10 |
| 3 | station rule, variable check, cite IDs inside text | 8/10 |
| 4 | supplier-lot root cause loaded, evidence expansion | 10/10 |
| 5 | same code, but default temperature 1.0 → randomness | 8/10, held-out 2/5 |
| 6 | temperature 0 + seed, general fixes, **fresh held-out set** | 10/10, **held-out 4/5** |

**Important lessons:**

- **10/10 is optimistic** because the prompt was tuned on those 10 questions (like tuning a model on its test set). The **held-out** questions were written before the run and never used for tuning. **4/5 is the number to quote.**
- The automatic check said 5/5; **reading by hand** found one answer led with the wrong (but real) work order. So the honest score is 4/5.
- **No answer in any run contained an invented fact.** Every failure was "I don't know" or, once, a real record in the wrong order. The safety design held.

**Remaining miss:** the model searched `name CONTAINS 'TC1 supply fan'` but the asset is called "Supply fan AHU-TC1". Next step: an entity-lookup tool (full-text index or the fuzzy matcher) before writing Cypher.

**No API key?** Offline mode uses fixed templates, so the pipeline and tests still pass. It is a baseline, not GraphRAG, and the report says so.

<div class="say">"The LLM never answers from memory. It only writes a Cypher query, which my code validates against the ontology and runs read-only. The answer must cite IDs that are in the result rows, or the sentence is removed. On unseen held-out questions I got 4 out of 5 after reading the answers myself, and no answer ever contained an invented fact."</div>

# Day 10 – Deliverables, three-band gate and link prediction (E3)

**Goal:** turn the working system into things a reviewer can use: predictions for the hidden test set, a report, slides, a demo; and add the bonus **E3 link prediction** for the hardest records.

## 10.1 Predictions for the hidden test set (`export.py`)

`outputs/predictions_tag_to_asset.csv` and `outputs/predictions_workorder_to_asset.csv`, in the same format as the TRAIN label files, plus:

- `confidence` (ML score), `band` (auto_accept / review / backlog), `method` (ml or engineer), `in_train` (leave these out when scoring).
- **Every record** gets its best guess, even review ones, so recall can be measured. Filter `band == auto_accept` to score only what enters the graph without a person.
- If an engineer rejected a link, that record is put in the backlog (not linked).
- Tests check: every one of the 1,541 tags has exactly one prediction with a valid band.

## 10.2 The final three-band gate

The assignment asks for three bands. On Day 10 the backlog threshold was also learned from data:

- **Auto-accept:** out-of-fold precision ≥ 0.995 and no wrong-machine error (WOs ≥ 0.932; tags ≥ 0.50).
- **Backlog:** scores where the top candidate was right **at most 25 %** of the time, measured on **at least 3** labelled records (WOs < 0.093). A reviewer would mostly reject these, so they go to a data-quality queue. **52 work orders.**
- **Review:** everything between.

## 10.3 E3 bonus: link prediction (`linkpred.py`)

**Idea in simple words:** "Work orders that use the same words as the records **already linked** to an asset are probably about that asset too." Example: many approved "cap tip dressing" WOs point to weld guns, so a new "tip dressing" WO probably belongs to a weld gun.

**How:**

- **Record vector** = TF-IDF of its tokens (equipment codes like L2 / ST04 / RB07 weighted ×3).
- **Asset vector** = its own tokens + the **average vector of its approved records** (one round of GraphSAGE-style mean aggregation, no learned weights).
- **Score** = cosine similarity, against **all 455 assets** (no candidate list from the matcher, so it is an *independent* opinion).

**First attempt failed:** a spectral (SVD) embedding gave hit@1 only **0.03**, because sibling robots (robot 07 on L1/L2/L3) share the same tokens. Using the approved links is what separates them.

**Results (out-of-fold, 5 folds):**

| | hit@1 | hit@5 | Matcher top-1 |
|---|---:|---:|---:|
| Tags | 0.954 | 0.996 | 1.000 |
| Work orders | 0.739 | 0.946 | 0.982 |
| All | **0.820** | 0.965 | 0.989 |

It is **weaker than the matcher** overall, and that is fine. Its value is on **hard cases**: on the 20 records the matcher got wrong or was unsure about, link prediction had the right asset in its **top 3 for 75 %**. So every backlog record goes to the review screen with link prediction's **top 3** as suggestions. **Never auto-accepted.**

**Example:** WO 4102478 "tip dresser Station 07 L1 blade broken". Matcher guessed an AGV (confidence 0.003). Link prediction suggested `DDN1-BIW-L1-ST07-TD` (0.88), which is clearly right.

## 10.4 Report, slides, notebook, demo, video

- **Report** (12 pages PDF): design decisions, results per part, honest limitations.
- **Slides** (31) with speaker notes, a live-demo slide and a code walkthrough map.
- **Profiling notebook** (`01_data_profiling.ipynb`), tested to run without errors.
- **Demo helper:** `python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV` (raw tag → graph node) and `python -m ddn.demo vin` (one car end to end).
- **One command:** `run_all.bat` (Windows) or `make all`: 18 steps + 102 tests, about 15 minutes the first time.
- **5-minute video** on YouTube.

<div class="say">"Link prediction is a second opinion, not a replacement. It's weaker than the matcher overall, hit@1 0.82, but on the records the matcher struggles with, the right asset is in its top 3 three times out of four. So I use it only to give the engineer a short list for backlog items. Never to auto-accept."</div>

# Top 50 interview questions with answers

Short answers you can speak in 30–60 seconds. Start with the main point, then one example.

## A. Big picture (1–8)

**1. Explain your project in two minutes.**
A car plant keeps data in separate systems (SAP assets, historian tags, MES/RFID, work orders, drawings, alarms, defects), and each names the same robot differently. I built a Python pipeline that cleans the data, links every record to one key (the SAP functional location) with rules plus a LightGBM model, sends unsure links to an engineer, and loads approved links into a Neo4j graph with provenance on every edge. On top I built anomaly detection linked to cars and defects, and a GraphRAG assistant that answers questions with citations.

**2. What is "contextualization"?**
Connecting a piece of data to the real thing it is about. Example: the tag `DDN1_BIW_L2_R07_WELDCUR.PV` is just a string until we know it is the weld current of robot RB07 at station 04 on body line 2. After that, we can join it with that robot's work orders, alarms and the cars it welded.

**3. What is a knowledge graph, and why use one here?**
Data stored as **nodes** (things) and **edges** (relationships). Our questions are chains of relationships: car → station → robot → anomaly → work order. A graph follows these chains directly; in SQL it would be many joins.

**4. Why is the functional location the canonical key?**
SAP is the system maintenance already trusts, and the FL already contains the hierarchy (`DDN1-BIW-L2-ST04-RB07`: plant, shop, line, station, robot). Every other name is mapped to it.

**5. What was the hardest part?**
Work orders. They are free text, sometimes Hinglish ("Rob 12 ka gun nahi chal raha"), and the SAP equipment number was wrong in 20 cases. Solving it needed text normalization, an "SAP number agrees with text" feature, and the review band.

**6. What are you most proud of?**
Zero wrong automatic links, and an honest evaluation: out-of-fold scores, a held-out set for GraphRAG, and reading answers by hand, which lowered my own score from 5/5 to 4/5.

**7. What is synthetic about the data and what does it mean for results?**
The names are more regular than in a real plant and there are only hundreds of labels. Real accuracy would be lower at first. That is why the review band and the feedback loop exist.

**8. How long does the full pipeline take?**
About 15 minutes the first time on a laptop (it creates the environment): 18 steps plus 102 tests. The heavy parts are VIN traceability and the graph load.

## B. Data and staging (9–14)

**9. What data-quality problems did you find?**
38 issues. Examples: oven temperatures in °F, 18 assets with missing parents, 231 duplicate alarms, a missed RFID reader, and SAP's `failure_code` not matching the text.

**10. How did you handle the °F values?**
Converted to °C at staging and verified: Oven 2 zone 3 median became 149.8 °C against a 150 °C set point.

**11. What is ISA-5.1 and why did you use it?**
The standard for instrument tags: TT = temperature transmitter, PT = pressure. Mapping signals to it gives a common vocabulary across PI, WinCC and S7, and helped fix a bug where `TT-301` was linked to the wrong unit.

**12. What does idempotent mean, and where does it matter?**
Running twice gives the same result. Parquet staging deletes its folder before writing (otherwise values duplicated), and the graph load uses `MERGE`, so re-runs never create duplicates.

**13. Why Parquet?**
Typed, compressed, columnar and fast. 1.1 million sensor values load in seconds, and it is the standard lakehouse format, so scaling up does not change it.

**14. Why did you not fix typos at staging?**
On purpose. Staging fixes only *documented* variants. Typos are the matcher's job, and leaving them shows exactly how much ML adds over rules.

## C. Entity matching (15–25)

**15. Why build a rules baseline first?**
It shows how hard the problem is, gives ML a number to beat, and rules are explainable. Rules gave tag F1 0.987, but 20 wrong work-order links, which showed what ML had to fix.

**16. How do rules get precision 1.000 on tags?**
The suffix index removes any key that points to more than one asset. Rules only link when the answer is unique; they never guess.

**17. What is blocking and why?**
Choosing a short candidate list (about 20 of 455 assets) before scoring, using TF-IDF top 15, equipment codes, rules and SAP answers, and parents/children. It makes matching fast and gives the model sensible pairs. Blocking recall is 1.000 for tags and 0.999 for WOs.

**18. Why character n-grams in TF-IDF?**
They tolerate typos. `BWI` and `BIW` share n-grams, while word-level TF-IDF would see them as different words.

**19. Name some features.**
Fuzzy similarity of name and FL, same line / station / equipment code (and conflicts), unit compatibility (kA → robot, Nm → nutrunner), rules agreement, SAP number agreement with text, how many candidates share the code, and time validity. 23 active features.

**20. Why LightGBM?**
Tabular features, small data, fast training, learns feature interactions by itself, gives feature importance. An LLM per pair would be slow, costly and hard to guarantee precision for.

**21. What is GroupKFold and why grouped?**
Cross-validation where all candidate pairs of one record stay in the same fold. Otherwise the model could see the correct pair for a record in training and be tested on the same record: scores would be inflated.

**22. How did you choose thresholds?**
From out-of-fold results: auto-accept where precision is ≥ 0.995 and there is no wrong-machine error above it (0.932 for WOs). Backlog where the top candidate was right ≤ 25 % of the time (below 0.093). Review in between.

**23. Why not threshold 0.5?**
At 0.5 there were 4 wrong automatic links, 3 to the wrong machine. At 0.932 there are zero, and only 12 more records need review. A review costs a minute; a wrong link can misdirect a recall.

**24. Near-miss vs wrong-machine error?**
Near-miss: right machine, wrong level (robot vs its own weld gun). Wrong-machine: a different robot or line. Wrong-machine errors are never allowed in auto-accept.

**25. Results of matching?**
Tags F1 1.000, WOs F1 0.982, 0 wrong auto-links; 99.4 % of tags and 95.9 % of WOs linked automatically.

## D. Documents, work orders, traceability (26–31)

**26. How did you read the scanned drawing?**
PyMuPDF detects no text layer → render at 300 and 400 dpi → Tesseract OCR in two layout modes → merge. 15 of 18 labels found; OCR links have lower confidence and go to review.

**27. How did you classify work-order failures?**
spaCy EntityRuler with phrase rules mapped to ISO 14224 codes, after translating Hinglish phrases. Rule-based, offline and traceable; all 8 root-cause WOs got the right mode.

**28. Why not use SAP's failure_code?**
It does not match the text: "water leak" WOs are coded LEAK only 20 % of the time, about chance. So it is not a reliable label.

**29. How did you fill missed RFID reads?**
Interpolate the car's own delay compared with the normal schedule between its real reads. Validated by hiding 2 % of real reads: median error 0.28 min. Marked `inferred` with `uncertainty_min`.

**30. What is processedBy and how is it built?**
Which machine worked on which car (511,182 edges). Robots and sealers are derived from the station passage and time; nutrunners are observed from torque results. Time-valid, so the moved robot only links to cars after its move.

**31. How do you handle the robot that moved lines?**
Two `partOf` edges: old one with `valid_to = 2026-03-01`, new one with `valid_from`. The matcher has a `valid_at_time` feature, and processedBy links only cars built after the move.

## E. Graph and ontology (32–38)

**32. Why Neo4j and not SQL?**
Multi-hop and variable-length paths are natural in Cypher, properties live on edges, and adding an edge type needs no table migration.

**33. Why not RDF?**
We need confidence, method and time on every edge. In RDF that needs reification or RDF-star. A property graph fits better; we can export to RDF if needed.

**34. What is provenance and why on every edge?**
Where a link came from and how sure we are: source_system, method, confidence, created_at, status. So "why does the graph say this?" is answered on the edge. The loader refuses edges without it; result: 0 edges without provenance.

**35. How many nodes and edges?**
165,706 nodes, 1,137,011 relationships. Biggest: processedBy 511 k and passedThrough 317 k (7,200 cars × about 44 stations).

**36. Why are sensor values not in the graph?**
A graph is good at relationships and bad at millions of numbers. The `TimeSeries` node holds a `store_uri` pointer to Parquet. Cognite and AWS do the same.

**37. How do you validate the graph after loading?**
Check every edge against the ontology's allowed from→to types, every edge has provenance, and every provenance value is in the allowed list. These checks caught two mistakes in my ontology.

**38. Explain one of the seven queries.**
D3: cars with low wheel-nut torque → the torque results → the tool (all TC14 → NR14) → its work orders. NR14 had no calibration in 12 months. The graph found a calibration gap that the alarm system missed, because the "calibration due" alarm fires on every nutrunner.

## F. Anomaly detection (39–43)

**39. Explain the robust z-score.**
z = (value − rolling 3-day median) / (1.4826 × rolling MAD). Median and MAD are not pulled by outliers like mean and standard deviation. An event starts at |z| > 6, continues while > 3, and must last at least 10 minutes.

**40. Why two baseline lags?**
12 h for sudden events; 1 day for slow wear. With only 12 h, a bearing that worsens over 4 days would become the new "normal" and be missed.

**41. Why not Isolation Forest?**
It found 6 of 8 in pieces, missed the stuck sensor, and raised 6 alerts with no cause. The z-score found 8/8 with no spurious alerts and is easy to explain. Isolation Forest is kept as a comparison.

**42. How do you decide if an anomaly is real?**
Written rules: flat line → sensor fault; exposed cars' defect rate ≥ 5× normal with ≥ 3 cases → quality problem; short oven over-temperature inside the bake window → false alarm; maintenance WO confirms it → equipment problem; nothing confirms → false alarm.

**43. Give an example of the context helping.**
AN-002 on nutrunner NR14: through processedBy we found the exposed cars; all 38 loose-wheel-nut defects were on them; WO 4102964 confirms a calibration problem. It was flagged 5½ hours before the first NOK result.

## G. GraphRAG and LLM (44–48)

**44. What is GraphRAG in your project?**
The LLM translates a question into Cypher using the ontology schema; my code validates and runs it read-only; the LLM writes an answer from the rows only, with citations; ungrounded sentences are dropped.

**45. How do you stop the LLM from damaging the database?**
Forbidden-keyword check, one statement only, labels/edges/properties/directions checked against the ontology, LIMIT added, and execution in a read-only transaction with a timeout. Even if a query passes the regex, Neo4j refuses writes.

**46. How do you stop hallucinations?**
"No citation, no claim": every sentence must cite IDs found in the result rows, otherwise it is removed. And there are three ways to say "I don't know". In all runs, no answer contained an invented fact.

**47. Why is 10/10 not the number you quote?**
The prompt was tuned on those 10 questions, so it is optimistic. I wrote held-out questions before running and never tuned on them: 4/5 after manual review. Also, temperature 0 and a fixed seed, because at temperature 1.0 the same code scored 8/10.

**48. What would you improve in GraphRAG?**
An entity-lookup tool (full-text index or the fuzzy matcher) so "AHU TC1 supply fan" becomes its FL before the query; a stricter grader (LLM judge or check the first claim); a tool to read time-series values via `store_uri`; more test questions.

## H. Bonus, scaling and reflection (49–50)

**49. What is link prediction (E3) and how do you use it?**
A second, independent opinion from graph structure: an asset's vector includes the average of its approved records, and we rank all 455 assets by cosine similarity. hit@1 0.82 overall; on hard records the right asset is in the top 3 for 75 %. Used only as top-3 suggestions for backlog items, never auto-accepted.

**50. How would you take this to production for many plants?**
Incremental loads instead of full reloads; one database or space per plant plus a shared space; high-volume event edges in a lakehouse with only what queries need in the graph; Airflow/Dagster to orchestrate steps; streaming via OPC UA/MQTT → Kafka; monitoring of band shares and review rejection rates; a secret manager for keys; and an enterprise LLM tenant for real data.

<div class="note"><b>Golden rules on the day.</b> (1) Answer the question first, then one example. (2) Say numbers only if you are sure; otherwise say the reason ("about a million edges, mostly station passes"). (3) Be honest about limits: interviewers trust candidates who say "this is optimistic because…". (4) If you don't know, say how you would find out.</div>
