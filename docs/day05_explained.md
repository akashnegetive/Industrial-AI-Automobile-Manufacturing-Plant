# Day 5 – ML entity matcher (Part C2, C3, C7 thresholds, C8)

| Code | Purpose |
|---|---|
| `src/ddn/textnorm.py` | Messy text → canonical tokens ("robot no 4 L2 gun" → `L2 RB04 WG`); Hinglish handling |
| `src/ddn/match_ml.py` | Blocking → pair features → LightGBM → cross-validation → thresholds → links |
| `reports/06_matching_ml.md` | Metrics, threshold trade-off, PR curves, every error |
| `data/staging/links_tag_name.parquet`, `links_wo_number.parquet` | Final link per record with confidence and band |

Run: `make ml` (about 1 minute) or `make all`.

## Results (out-of-fold, 5-fold cross-validation grouped by record)

| Source | Rules only F1 | ML F1 | Wrong links in auto-accept band | Blocking recall |
|---|---:|---:|---:|---:|
| Tags (539) | 0.987 | **1.000** | 0 | 1.000 |
| Work orders (888) | 0.950 | **0.981** | **0** (rules: 20) | 0.999 |

All 1,541 tags: 1,534 auto-accepted, 7 to review. All 2,968 work orders: 2,829 auto-accepted, 108 to review, 31 to the backlog.

## 1. Text normalisation (`textnorm.py`)

One extractor runs on asset names, tag names and work-order text, so the matcher compares like with like.

| Input | Tokens |
|---|---|
| `R7 gun tip dressing fail` | `RB07 WG` |
| `Rob 12 ka gun nahi chal raha` | `RB12 WG` (Hinglish → "not running") |
| `DC tool 14` / `Nutrunner 14` / `NR14` | `NR14` |
| `Sealer robo 3` | `SR03` |
| `Chiller CH-01` vs `CH1 NR11` | `CH01` (chiller) vs `CH1` (chassis line) |
| `PaintShop-Ovn02-Z3FAN-Spd` | `OV2 Z3 FAN` (glued codes split first) |

**Order matters:** "Sealer robo 3" must be handled *before* "robo" → "robot", otherwise it also produces `RB03`. A test locks this in.

## 2. Candidate generation, also called blocking (C2)

Comparing every record with all 455 assets would be slow, and it gives the classifier mostly pointless pairs. Each record gets the union of:
1. the top 15 assets by **character n-gram TF-IDF** (2–4 characters, so `BWI` still resembles `BIW`);
2. every asset whose equipment code appears in the text. "R7" with no line gives robot 7 on L1, L2 **and** L3;
3. the rules answer and the SAP-number answer;
4. parents and children of the above (robot ↔ weld gun, nutrunner ↔ controller).

That averages about 20 candidates per record instead of 455. **Blocking recall** is 1.000 for tags and 0.999 for work orders (one work order lost). A true asset missing here can never be recovered later, which is why it's reported separately.

## 3. Pair features (C3)

For each (record, candidate) pair the features ask: *does this candidate agree with what the record says?*

| Group | Features |
|---|---|
| String similarity | `tfidf`, `fuzz_name` (rapidfuzz token-set ratio against the asset name), `fuzz_fl` |
| Token agreement | `equip_match/conflict`, `line_match/conflict`, `station_match/conflict`, `comp_match/conflict/parent`, `shop_match` |
| Domain | `unit_compat`: kA fits a robot, Nm fits a nutrunner, %RH fits an AHU |
| Other sources | `rule_match`, `rule_conf`, `eqno_match`, `eqno_present`, `fltext_match` |
| Trust in the SAP number | `eqno_text_agree`: does the text confirm the equipment number? |
| Ambiguity | `n_equip_cands`: how many candidates share the equipment code (L1/L2/L3) |
| Optional | `embed`: sentence-transformers cosine. Off here because Hugging Face is blocked; it switches on automatically when the library and model are installed |

**Why `eqno_text_agree` was added:** the first model trusted the SAP number blindly, so "Nutrunner 01 annual calibration" followed a wrong number. With the agreement feature, the model can learn *when* to distrust the number.

## 4. Model and evaluation (C3, C8)

- **LightGBM** (gradient-boosted trees). It handles mixed feature types and interactions like "SAP number present *but* the text contradicts it" without manual feature crosses.
- **Cross-validation grouped by record:** all candidate pairs of one work order stay in the same fold, so the model never sees the answer for a record it's being tested on. Every metric in the report is out-of-fold.
- The record's answer is its **highest-probability candidate**, and that probability is the confidence.

## 5. Thresholds from the precision curve (C7)

| Band | Rule | Work orders |
|---|---|---|
| Auto-accept | lowest confidence where out-of-fold precision ≥ 0.999 (floor 0.5) | ≥ 0.89 |
| Review | below auto, while the next band of 20 records is still ≥ 50 % correct | ≥ 0.01 |
| Backlog | the rest (data-quality queue) | < 0.01 |

The trade-off table in the report shows the choice: at 0.50 there are 4 wrong auto-links; at 0.90 there are 0, at the cost of only 11 more records to review. A wrong automatic link can send a recall investigation to the wrong robot, while a review costs an engineer a minute.

## 6. What remains wrong (17 work orders, all in review or backlog)

- **No line in the text:** "R7 dress pack…", "Rob 03…". Robot 7 exists on three lines. Only the SAP number or a person can decide.
- **No equipment at all:** "WG water leak at cap adaptor", "TC controller comm fault".
- **Label conventions:** "L2 RB12 ka gun nahi chal raha" is labelled the robot, not its gun.
- **Time:** "R12 …" written before March 2026 means L1's robot 12. That robot moved, so the graph's time-valid `partOf` handles it (Day 7).

## 7. Honest caveats
- Tag F1 = 1.000 is on synthetic data with 539 labels. Real plant data would have more naming conventions and no clean asset master. A sample of real tags would need to be labelled to find out.
- The thresholds are fitted on the same out-of-fold predictions they're reported on. Labels from engineer review (Day 7) should be used to re-check them.
- Synthetic Hinglish covers a few phrases. Real shorthand would need a bigger vocabulary built from reviewer corrections.

## Exercises
- Set `AUTO_PRECISION = 0.99` and run `make ml`. How many wrong auto-links come back?
- Remove `eqno_text_agree` from `FEATURES` and compare the work-order errors.
- Pick three rows from "Out-of-fold errors" and decide what *you* would answer as a reviewer, and why.
