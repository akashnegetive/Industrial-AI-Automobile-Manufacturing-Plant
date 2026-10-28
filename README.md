# Plant DDN-01 – Contextualization & Knowledge Graph

Industrial AI take-home assignment: link siloed car-plant data to one asset model, load it into a knowledge graph, and use it for anomaly detection and grounded Q&A.

## Run

**Windows laptop: full setup, daily update commands and expected output are in [`docs/LAPTOP_SETUP.md`](docs/LAPTOP_SETUP.md).**

1. From the unzipped candidate pack, copy
   - the `data/` files into `data/raw/` (see `data/raw/README.md`), and
   - the `documents/` folder into `docs/source_pack/` (see `docs/source_pack/README.md`).
2. Run everything (first run also creates `.venv` and installs requirements):

| System | One command |
|---|---|
| Windows | double-click `run_all.bat`, or in PowerShell: `.\run_all.ps1` |
| Mac / Linux | `make setup` (first time), then `make all` |

Both run the same steps (`src/ddn/pipeline.py`): reports in `reports/`, staging tables in `data/staging/`, then the tests.

Optional: install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) to read the scanned drawing; without it that one drawing is skipped.

Start reading at `docs/LEARNING_GUIDE.md`; each day's work is explained in `docs/dayNN_explained.md`.

## Progress
| Part | Status | Output |
|---|---|---|
| B.1 Dataset profiles | done | `reports/01_dataset_profile.md` |
| B.2 Data-quality report (37 issues) | done | `reports/02_data_quality.md` |
| B.3 Identity schemes | done | `reports/03_identity_schemes.md` |
| B.4 Production problems (9, with evidence) | done | `reports/04_production_problems.md` |
| A Vendor research | draft, links to verify | `docs/part_a_research.md` |
| D Ontology v1 (18 node, 18 edge types) | done | `ontology/ontology_v1.yaml`, `docs/ontology.md` |
| C1 Staging (typed Parquet, deg F -> deg C) | done | `data/staging/` (generated) |
| C Rules baseline: tags F1 0.987, work orders F1 0.950 | done | `reports/05_matching_rules_baseline.md` |
| C ML matcher: tags F1 1.000, work orders F1 0.982, 0 wrong auto-links | done | `reports/06_matching_ml.md` |
| C5 Documents: 145 drawing labels (incl. OCR of the scan), manual alarm codes + failure modes | done | `reports/07_documents.md` |
| C4 Work-order failure modes (ISO 14224, spaCy) | done | `reports/08_workorders.md` |
| MES stations, `feeds` edges, alarm sources | done | `reports/09_stations_alarms.md` |
| C6 VIN traceability (missed reads inferred + validated) | done | `reports/10_vin_traceability.md` |
| C7 Review queue + Streamlit review screen; decisions reused as labels | done | `apps/review_app.py`, `data/review/decisions.csv` |
| D Neo4j graph: 165,698 nodes, 1.13 M edges, provenance on every edge | done | `reports/11_graph_load.md` |
| D Seven graph queries (Cypher) | done | `reports/12_graph_queries.md` |
