# AI_USAGE – checks still to do

Do each check, then write in docs/AI_USAGE.md (main branch), in the "How I verified" cell of that row, what you did, in your own words and in the past tense.

| Row | Files | Check to do |
|---|---|---|
| Day 1 | src/ddn/config.py, load.py, profile.py, tests/test_load.py,  | Compare the row counts in reports/01_dataset_profile.md with the assignment PDF page 2 (455 assets, 1,541 tags, 1,101,823 values, 7,200 VINs, 310,462 passages, 79,855 torque results, 64,800 part-lot records, 675 defects, 2,968 work orders, 7,917 alarms). |
| Day 2 | src/ddn/quality.py, identity.py, problems.py, tests/test_day | Open alarms_andon_events.csv, search the source column for `/S3/`, and confirm entries like `PNT/SL/S3/SR06` exist (DQ issue 2). |
| Day 3 | ontology/ontology_v1.yaml, src/ddn/ontology.py, tests/test_o | Compare the node and edge types in docs/ontology.md with the minimum list in the assignment PDF page 4 (Part D). |
| Day 4 | src/ddn/tags.py, match_rules.py, evaluate.py, tests/test_day | Run `python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV` and confirm the parsed line, equipment and asset match the row for that tag in labels_tag_to_asset_TRAIN.csv. |
| Day 5 | src/ddn/textnorm.py, match_ml.py, tests/test_day5.py, docs/d | Pick one out-of-fold error in reports/06 (e.g. WO 4101050) and look it up in maintenance_work_orders.csv and the TRAIN labels. |
| Day 10 | src/ddn/export.py, demo.py, notebooks/01_data_profiling.ipyn | Run `python -m ddn.demo tag` and `python -m ddn.demo vin` on my laptop; read the report and check three numbers against reports/ (e.g. F1 0.982 in reports/06, 1,492 in reports/12, AN-008 false alarm in reports/13). |
| Day 10 | slides/DDN01_interview.pptx, slides/build_slides.js, docs/SU | Rehearsed the slides once with a timer and corrected anything I would say differently. |
| Day 10 | match_ml.thresholds() (backlog band), review.py backlog + E3 | Open the review screen: check a "[suggested by link prediction]" item, e.g. WO 4100629, and the Backlog tab |
