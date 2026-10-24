# Day 4 – Staging, tag parser and rules-only baseline (Part C)

| Step | Code | Output |
|---|---|---|
| C1 Ingest + normalise | `src/ddn/tags.py` | `data/staging/tags.parquet`, `assets.parquet`, `timeseries/` |
| Rules matchers | `src/ddn/match_rules.py` | `data/staging/tag_matches_rules.parquet`, `wo_matches_rules.parquet` |
| C8 Measure | `src/ddn/evaluate.py` | `reports/05_matching_rules_baseline.md` |

Run: `make match` (staging + matching + evaluation) or `make all`.

## Results

| Source | Precision | Recall | F1 | Wrong links | Coverage of all records |
|---|---:|---:|---:|---:|---:|
| Tags (539 TRAIN labels) | 1.000 | 0.974 | 0.987 | 0 | 97.5 % of 1,541 |
| Work orders (888 TRAIN labels) | 0.976 | 0.925 | 0.950 | 20 | 93.7 % of 2,968 |

## 1. Staging (`tags.py`) – Part C1

**What it does**
- Parses every tag into `shop / line / equip / signal` with one regex per source system (PI, WinCC, S7, MES).
- Validates each parsed tag through a pydantic `TagRecord`.
- Adds an ISA-5.1 code from the signal: `TEMP` → `TT`, `PRESS` → `PT`, `RH` → `MT` (moisture), `VIB` → `VT`, and so on.
- Converts °F to °C in the time series. Oven 2 zone 3 now has a median of 149.8 °C against its 150 °C setpoint, which confirms the conversion.
- Repairs the 18 missing parents by walking up the FL path until an existing asset is found. This also works for dies like `D-BSO-LH-03`.
- Stores values as Parquet **partitioned by tag**. The graph will later store just the pointer (`store_uri`).

**What it normalises, and what it deliberately doesn't**
| Normalised (documented variants) | Left alone (typos) |
|---|---|
| WinCC areas: Oven2 / OVN2 / Ovn02 / Oven1 / EDOven / EcoatOven / AirHandling | `DN1_`, `DD1_`, `BWI`, `2L`, `S0T3FX` |
| `R07` → `RB07` (PI vs SAP robot naming) | `P2RHOL`, `PR4L.UBEP`, `R0`, `F_AFN1` |
| Legacy controller name `L1ST3_RB5` (flagged `legacy_name`) | |

The rules matcher *should* fail on typos. Fixing them is the job of the fuzzy/ML matcher (Day 5), and the gap between the two is what the comparison in C8 measures.

**Idempotency bug found and fixed:** writing a partitioned Parquet folder a second time *adds* files, so every value would have been duplicated. The stage step now deletes the folder first, and the row count is checked: 1,101,823 in, 1,101,823 out.

## 2. Rules matcher for tags (`match_rules.py`)

**The index trick.** For every equipment or component asset, store every *suffix* of its path below the line:
```
DDN1-BIW-L2-ST04-RB07   → (BIW, L2, "ST04RB07"), (BIW, L2, "RB07")
DDN1-PNT-PT-T106-P106   → (PNT, PT, "T106P106"), (PNT, PT, "P106")
DDN1-PNT-OV2-Z3-FAN     → (PNT, OV2, "Z3FAN"), (PNT, OV2, "FAN")  ← FAN is ambiguous, dropped
```
A key that points at more than one asset is removed, so a lookup can never pick between two assets. That's why precision is 1.000: the rules link only when the answer is unique.

**Rules and confidence**
| Rule | Fires when | Confidence |
|---|---|---|
| relocation | Legacy name, and an asset description says "Relocated from L1 ST03 (ex R05)" | 0.95 |
| exact | Tag follows its documented convention | 0.99 |
| alias | Same, but a WinCC area spelling was normalised | 0.97 |

The relocation rule is **driven by data, not hard-coded**: it reads the asset description. If a second robot moves, it works without code changes.

**Zero-padding decision.** SAP has both `AGV07` (padded) and `P1` (not padded), so the matcher tries the token as written and then padded. My first version always padded, which broke 4 EOL pump tags; the failure report showed it.

## 3. Rules matcher for work orders

It uses only structured fields, in order of reliability: FL text that is a path fragment (0.97), FL text equal to a *unique* asset name (0.90), then the SAP equipment number (0.85). "Robot 07" exists on three lines, so it's never used as a name match.

**Key finding:** all 20 wrong links come from the SAP equipment number. A key from the source system isn't ground truth. Day 5's matcher must cross-check the number against the text ("weld gun L1 RB04…") and override it when they disagree.

## 4. Evaluation (`evaluate.py`)

```
precision = TP / (TP + FP)     when we link, how often we're right
recall    = TP / (TP + FN)     how many true links we find
F1        = 2PR / (P + R)
```
A **wrong** prediction counts as both FP (a bad edge) and FN (the right edge is missing). That's deliberate: in a recall investigation a wrong edge is worse than a missing one. The test `test_score_counts_wrong_link_as_fp_and_fn` locks this in.

**Honest caveat.** The rules use no labels, but they were *designed* after reading the TRAIN labels (for example, robot signals belong to the robot, not its weld gun), and the padding bug was fixed after seeing TRAIN failures. TRAIN scores are therefore slightly optimistic. The evaluator's hidden labels are the real test, and Day 5 will use cross-validation so the ML numbers aren't inflated in the same way.

## 5. What Day 5 has to beat
- **Tags:** 14 typo tags, with 0 wrong links allowed. Rules are already at F1 0.987, so ML must not add wrong links.
- **Work orders:** 47 with no structured identifier (text only) plus 20 wrong equipment numbers. This is where ML earns its place.

## Exercises
- Remove the `_pad` fallback in `RulesMatcher.match` and run `make match`. Which tags drop out?
- Add a fake relocation to an asset description in a copy of the data and check the relocation rule picks it up.
- Open `reports/05_matching_rules_baseline.md` and classify the 14 missed tags by typo type (missing letter, swapped letters, wrong separator).
