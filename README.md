# Plant DDN-01 – Contextualization & Knowledge Graph

A Python pipeline that links the siloed records of a car plant (SAP assets, historian tags, MES/RFID, work
orders, drawings, alarms, defects) to one asset hierarchy. It loads them into a **Neo4j knowledge graph with
provenance on every edge**, then uses the graph for **anomaly detection** and **grounded question answering
(GraphRAG)**. Built on the synthetic Plant DDN-01 data pack (1–14 Sep 2026).

**Report:** [`report/REPORT.pdf`](report/REPORT.pdf) · **Slides:** [`slides/DDN01_interview.pptx`](slides/DDN01_interview.pptx) · **Demo video (5 min):** *link to be added*

## Results

| | Result |
|---|---|
| Entity matching (out-of-fold on TRAIN labels) | Tags **F1 1.000**, work orders **F1 0.982**; **0 wrong auto-accepted links** |
| Automatically contextualized | 99.4 % of tags, 95.9 % of work orders. Three-band gate as in the assignment: auto-accept / review / backlog (52 work orders, threshold from the out-of-fold data) |
| E3 bonus: link prediction | Graph-embedding second opinion for the backlog: hit@1 0.82 overall; on records the matcher got wrong or was unsure about, the right asset is in its top 3 for 75 % |
| Knowledge graph | 165,706 nodes, 1,137,011 relationships, 0 edges without provenance, 0 ontology violations |
| Anomaly detection | 8 / 8 seeded signal problems found, each linked to equipment, VINs, defects and a work order; 1 judged a false alarm, with reasons |
| GraphRAG | 10 / 10 on the evaluation set, **4 / 5 on unseen held-out questions** (manually reviewed; the automatic check said 5 / 5); no answer in any run contained an invented fact |

The hidden-test predictions for Part C are in [`outputs/`](outputs/): every tag and work order, with confidence
and band.

## Run it (one command)

1. From the candidate pack, copy the `data/` files into `data/raw/` and the `documents/` folder into
   `docs/source_pack/` (the pack is not in this repository).
2. Run:

| System | Command |
|---|---|
| Mac / Linux | `docker compose up -d && make all` |
| Windows | `run_all.bat` (double-click), or `.\run_all.ps1` in PowerShell |

Needs **Python 3.11+** and **Docker** (Neo4j 5 Community runs in it). The first run creates `.venv`, installs
the requirements and takes about 15 minutes: 18 steps, then 102 tests. Expected output per step is in
[`docs/LAPTOP_SETUP.md`](docs/LAPTOP_SETUP.md).

Optional:
- **Tesseract OCR**, to read the one scanned drawing (otherwise it is skipped).
- **`OPENAI_API_KEY`**, for GraphRAG with an LLM. Without it, the step runs an offline template baseline, so
  the pipeline and the tests still complete.

## How it works

```
sources ──► staging ──► blocking ──► rules + LightGBM ──► confidence gate ──► Neo4j graph ──► anomalies (E1)
(SAP, tags, (pydantic,  (TF-IDF     (20 pair features,    auto-accept │        (provenance,    GraphRAG (E2)
 MES, WOs,   units,      top-15)     out-of-fold CV)      review ─────┘        time-valid      queries D1–D7
 drawings…)  ISA-5.1)                                     (Streamlit)          partOf; values
                                                                               in Parquet)
```

- **Canonical key:** the SAP functional location (`DDN1-BIW-L2-ST04-RB07`); every other identifier is linked to it.
- **Thresholds by cost:** auto-accept only where the out-of-fold precision is ≥ 0.995 with no wrong-machine
  error; a backlog below the score where top candidates were mostly wrong; the review screen in between. Each
  engineer decision becomes an edge and a training label. Backlog records get link prediction's top 3 (E3).
- **Ontology first:** [`ontology/ontology_v1.yaml`](ontology/ontology_v1.yaml) (v1.3, 18 node and 19 edge types)
  drives the loader, the validation and the GraphRAG schema. Rendered as [`docs/ontology.md`](docs/ontology.md).
- **GraphRAG safety in code:** LLM-written Cypher is validated against the ontology and run read-only;
  every sentence must cite IDs found in the result rows.

The design decisions and their reasons are in the report, section 3.

## Try it

```bash
python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV   # one robot tag: raw name -> graph node
python -m ddn.demo vin                              # one VIN traced end to end
streamlit run apps/review_app.py                    # engineer review screen (approve / reject / correct)
streamlit run apps/ask_app.py                       # ask the plant (GraphRAG)
```
Run these with `PYTHONPATH=src` and the `.venv` Python. The Neo4j browser is at http://localhost:7474
(user `neo4j`, password `ddn-plant-2026`).

## Deliverables

| Assignment part | Where |
|---|---|
| A – Vendor research (Cognite, Siemens, AWS) | [`docs/part_a_research.md`](docs/part_a_research.md), report section 1 |
| B – Profiles, data quality (38 issues), identity schemes, 9 production problems | [`notebooks/01_data_profiling.ipynb`](notebooks/01_data_profiling.ipynb), [`reports/01`–`04`](reports/) |
| C – Matching (rules vs ML), documents/OCR, work orders (ISO 14224), VIN traceability, review | [`reports/05`–`10`](reports/), [`apps/review_app.py`](apps/review_app.py), [`outputs/`](outputs/) |
| D – Ontology, graph load, the 7 queries | [`ontology/`](ontology/), [`reports/11`–`12`](reports/) |
| E – Anomaly detection, GraphRAG, E3 link prediction (bonus) | [`reports/13`–`15`](reports/), [`apps/ask_app.py`](apps/ask_app.py) |
| Report, slides, demo script | [`report/`](report/), [`slides/`](slides/), [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) |
| AI-assistant disclosure | [`docs/AI_USAGE.md`](docs/AI_USAGE.md) |

## Repository layout

```
src/ddn/        pipeline code; pipeline.py holds the step list used by make all and run_all
apps/           Streamlit screens: review_app.py, ask_app.py
ontology/       ontology_v1.yaml (versioned, with changelog)
reports/        generated reports 01–14 (Markdown, regenerated on every run)
outputs/        predictions for the hidden test set
tests/          pytest suite (102 tests; graph tests skip if Neo4j is not running)
notebooks/      data profiling notebook
report/ slides/ final report (PDF + Markdown source) and interview slides
docs/           Part A research, ontology docs, laptop setup, demo guide, AI-assistant disclosure
data/raw/       the data pack goes here (not committed)
```

## Limitations

The full list is in the report, section 5. In short: scores are out-of-fold on the TRAIN labels, so the hidden
test set is the real measure. The data is synthetic and its naming more regular than a real plant's. 4 of the 8
root-cause work orders wait in the review band. Root causes are stored as hypotheses (`status=suggested`).
GraphRAG was evaluated on 20 questions with a lenient automatic check (answers were also read by hand) and sends data to OpenAI, which is acceptable only for synthetic data.

Synthetic data only: no real customer or employer data is used.
