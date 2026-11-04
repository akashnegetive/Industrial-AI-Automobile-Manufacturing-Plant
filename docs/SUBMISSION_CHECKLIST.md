# Submission checklist (assignment section 8)

| Deliverable | Where | Status |
|---|---|---|
| Git repo, README, one command (`docker compose up -d && make all`, or `run_all.bat`) | README.md | done; tested on a fresh clone |
| Data profiling notebook | notebooks/01_data_profiling.ipynb | done |
| Data-quality report, ontology file, pipeline code, graph loader, AI layer, tests | reports/02, ontology/, src/ddn/, tests/ (102) | done |
| Report, 8–12 pages: Part A, design decisions, metrics, limitations, real-plant changes | report/REPORT.pdf (12 pages) | done; Part A links checked |
| 5-minute demo video: one robot tag → graph node, one VIN end to end | recorded; guide in docs/demo_video/DEMO_VIDEO_GUIDE.pdf | **edit, upload, put the link in the README** |
| Slides for the 45-minute interview | slides/DDN01_interview.pptx (31 slides, speaker notes) | done; **rehearse** |
| Hidden-test predictions (Part C is scored on them) | outputs/predictions_*.csv | done |
| AI-assistant disclosure | docs/AI_USAGE.md | **finish the [to do] rows** |

## Still to do (only you can)

1. **Video:** finish editing, upload as *Unlisted* (YouTube) or share from Google Drive ("Anyone with the
   link"), and replace *"link to be added"* in the third line of README.md (or send the link to have it added).
2. **docs/AI_USAGE.md:** do the remaining **[to do]** checks, rewrite each in your own words in the past tense,
   then delete the `<!-- DRAFT ... -->` comment near the top. Every line must be true: interview question 6.
3. **Rehearse the slides once with a timer** (slide 2 has the 45-minute plan; the speaker notes say what to explain).
4. **Optional:** commit `data/review/decisions.csv` if you want the evaluators to see your review decisions.
5. **On the day:** `git pull`, `run_all.bat` once, then start Neo4j and both Streamlit screens (after the pull).

## What to send

> Repository: https://github.com/akashnegetive/Industrial-AI-Automobile-Manufacturing-Plant
> Demo video: (your link)
> Report: report/REPORT.pdf · Slides: slides/DDN01_interview.pptx (both in the repository)

Before sending, open the repository link in a private/incognito browser window to check that it's visible to
others. It must be public, or the interviewers must be added as collaborators.
