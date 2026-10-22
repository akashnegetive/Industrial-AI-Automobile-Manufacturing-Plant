PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: setup profile test all
setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
profile:
	$(PY) -m ddn.profile
test:
	$(PY) -m pytest -q
all: profile test
