# Plant DDN-01 – Contextualization & Knowledge Graph

Industrial AI take-home assignment: link siloed car-plant data to one asset model, load it into a knowledge graph, and use it for anomaly detection and grounded Q&A.

## Run
1. Copy the candidate-pack `data/` files into `data/raw/` (see `data/raw/README.md`).
2. Then:
```bash
make setup   # create venv, install requirements
make all     # run pipeline steps + tests
```

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
