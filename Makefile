PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: setup profile quality identity problems reports test all
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
reports: profile quality identity problems
test:
	$(PY) -m pytest -q
all: reports test
