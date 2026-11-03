# AI assistant usage log

The assignment requires disclosing AI-assistant use. Fill in "How I verified" yourself after reviewing each file.

| Date | File(s) | What the AI did | How I verified |
|---|---|---|---|
| Day 1 | src/ddn/config.py, load.py, profile.py, tests/test_load.py, Makefile | Drafted project skeleton, typed loaders, dataset profiler | |
| Day 1 | docs/LEARNING_GUIDE.md, docs/day01_explained.md | Drafted learning notes | |
| Day 2 | src/ddn/quality.py, identity.py, problems.py, tests/test_day2.py | Exploration scripts, drafted DQ checks, identity table, problem evidence chain | |
| Day 2 | docs/day02_explained.md | Drafted explanation notes | |
| Day 3 | docs/part_a_research.md | Ran web searches over vendor docs and drafted the comparison; every claim still to be checked against the live pages | |
| Day 3 | ontology/ontology_v1.yaml, src/ddn/ontology.py, tests/test_ontology.py, docs/day03_explained.md | Drafted ontology, validator, doc generator, tests | |
| Day 4 | src/ddn/tags.py, match_rules.py, evaluate.py, tests/test_day4.py, docs/day04_explained.md | Drafted parser, staging, rules matchers, evaluation and tests | |
| Day 5 | src/ddn/textnorm.py, match_ml.py, tests/test_day5.py, docs/day05_explained.md | Drafted normaliser, candidate generation, features, LightGBM CV, threshold logic | |
| Day 6 | src/ddn/documents.py, workorders.py, context.py, trace.py, tests/test_day6.py, docs/day06_explained.md; fixes in match_ml.py, textnorm.py | Drafted document/OCR extraction, spaCy failure modes, station/alarm linking, VIN traceability; found and fixed matcher bugs | |
| Day 7 | docker-compose.yml, src/ddn/review.py, apps/review_app.py, graph.py, queries.py, tests/test_day7.py, ontology v1.1.0, docs/day07_explained.md | Drafted review queue/app, Neo4j loader with provenance + validation, seven Cypher queries | |
| Day 8 | src/ddn/anomaly.py, graph.py (anomalies), queries.py (E1), review priority, ontology v1.2.0, tests/test_day8.py, docs/day08_explained.md | Prototyped and built detectors, context linking, judgement rules, Isolation Forest comparison | |
| Day 9 | src/ddn/graphrag.py, apps/ask_app.py, ontology v1.3.0, tests/test_day9.py, docs/day09_explained.md | Drafted the GraphRAG loop (OpenAI/Claude/Ollama providers, Cypher validator, citation grounding, offline baseline) and the 10-question evaluation | |
| Day 10 | src/ddn/export.py, demo.py, notebooks/01_data_profiling.ipynb, report/ (REPORT.md, build.py, report.css), docs/DEMO_SCRIPT.md, tests/test_day10.py | Drafted the predictions export, demo helper, profiling notebook, report text from the generated reports, PDF build and video script | |
| Day 10 | slides/DDN01_interview.pptx, slides/build_slides.js, docs/SUBMISSION_CHECKLIST.md | Drafted the slide deck and speaker notes from the report and generated results | |
