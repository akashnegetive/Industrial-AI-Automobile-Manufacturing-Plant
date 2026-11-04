# Submission checklist (assignment section 8)

| Deliverable | Where | Status |
|---|---|---|
| Git repo, README, one command (`docker compose up` + `make all`, or `run_all.bat`) | README.md | done |
| Data profiling notebook | notebooks/01_data_profiling.ipynb | done |
| Data-quality report, ontology file, pipeline code, graph loader, AI layer, tests | reports/02, ontology/, src/ddn/, tests/ (99) | done |
| Report, 8–12 pages: Part A, design decisions, metrics, limitations, real-plant changes | report/REPORT.pdf (11 pages) | done (12 pages; Part A links checked) |
| 5-minute demo video: one robot tag → graph node, one VIN end to end | docs/DEMO_SCRIPT.md; helpers `python -m ddn.demo tag` / `vin` | **you record it** |
| Slides for the 45-minute interview | slides/DDN01_interview.pptx (30 slides, speaker notes) | done, **rehearse** |
| Hidden-test predictions (Part C is scored on them) | outputs/predictions_*.csv | done |

## Still to do (only you can)

1. **Check the Part A links.** Open every link in `docs/part_a_research.md` in a browser and confirm each
   claim says what the page says (the build environment couldn't reach the vendor sites). Fix anything
   wrong, delete the yellow "Source status" note in `report/REPORT.md` and `docs/part_a_research.md`, then
   rebuild the PDF (`python report/build.py`, which needs pandoc + Node Playwright) or ask for a rebuild.
2. **Fill in "How I verified"** in `docs/AI_USAGE.md` (the interviewers will ask: question 6).
3. **Record the demo video** with `docs/DEMO_SCRIPT.md`; upload it unlisted and put the link in the README.
4. **Rehearse the slides once with a timer.** About 25 minutes of talk leaves room for the code walkthrough
   and questions. The speaker notes say what to explain on each slide; the last 2 slides are backup answers to
   the 7 interview questions.
5. **Final run on the laptop** (`run_all.bat`), then commit `reports/14_graphrag.md` from that run so GitHub
   shows the OpenAI result.
