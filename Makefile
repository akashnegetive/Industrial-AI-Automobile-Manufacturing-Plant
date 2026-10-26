PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: setup profile quality identity problems ontology stage match ml reports test all
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
profile:            ## Part B.1 dataset profiles
	$(PY) -m ddn.profile
quality:            ## Part B.2 data-quality report
	$(PY) -m ddn.quality
identity:           ## Part B.3 identity schemes
	$(PY) -m ddn.identity
problems:           ## Part B.4 production problems with evidence
	$(PY) -m ddn.problems
ontology:           ## Part D ontology: validate YAML + render docs/ontology.md
	$(PY) -m ddn.ontology
stage:              ## Part C1 typed staging tables (Parquet), deg F -> deg C
	$(PY) -m ddn.tags
match: stage        ## Part C rules baseline + evaluation on TRAIN labels
	$(PY) -m ddn.evaluate
ml: stage           ## Part C ML matcher (TF-IDF blocking + LightGBM), CV metrics, thresholds
	$(PY) -m ddn.match_ml
reports: profile quality identity problems ontology match ml
test:
	$(PY) -m pytest -q
all: reports test
