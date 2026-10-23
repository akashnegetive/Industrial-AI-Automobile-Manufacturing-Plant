# Day 2 – Data quality, identity schemes, production problems (Part B)

Part B asks for four things. Day 1 delivered the first; today delivers the other three.

| Deliverable | Code | Report |
|---|---|---|
| B.1 Profile of every dataset | `src/ddn/profile.py` | `reports/01_dataset_profile.md` |
| B.2 Data-quality report with evidence | `src/ddn/quality.py` | `reports/02_data_quality.md` |
| B.3 Table of identity schemes | `src/ddn/identity.py` | `reports/03_identity_schemes.md` |
| B.4 Real production problems | `src/ddn/problems.py` | `reports/04_production_problems.md` |

Run everything with `make all`, or one step at a time with `make quality`, `make identity` or `make problems`.

---

## 1. How I worked: explore first, then code

I didn't write `quality.py` straight away. I first ran throw-away exploration scripts: daily averages per tag, defect counts per day, crosstabs. Each **finding** then became a **check function**. That's the order to describe in the interview: *"I explored, formed hypotheses, then encoded each one as a repeatable check with evidence."*

---

## 2. `quality.py` – the data-quality report

### The `Issue` model (pydantic)
```python
class Issue(BaseModel):
    dataset: str; check: str; severity: str; count: int
    evidence: list[str]; impact: str; documented: bool = False
```
- **pydantic** validates types. If a check returns a count as text, it fails loudly. The assignment asks for pydantic in Part C1, so we start using it here.
- **evidence** holds concrete example rows a reviewer can look up, because the assignment says "with evidence".
- **impact** answers "so what?": what each issue means for matching or analysis.
- **documented** marks whether the data dictionary already lists the issue. **14 of 37 are new**, which shows you went beyond the dictionary.

### The checks worth knowing in detail
| Check | Technique | Why it's interesting |
|---|---|---|
| Missing parent | `parent_functional_location.isna()` | 18 assets (~4 %). Fix: the parent is the FL minus its last segment… |
| Dies contain `-` | implied parent not found | …except for dies (`D-BSO-LH-03`), where that rule breaks |
| Misspelt names | `rapidfuzz.fuzz.ratio` of rare words against common words | "Buner" → "Burner", "Fixtre" → "Fixture" |
| Tag-name typos | one regex per source system | `DD1_`, `DN1_`, `F_AFN1_`, `CLMP.1PV` |
| Historian outage | minutes where **all** tags are missing | 9 Sep 02:00–02:44 |
| Stuck sensor | longest run of identical values (`(v.diff() != 0).cumsum()` gives a run id) | TT-301 frozen for 569 min, **marked "Good"** |
| Duplicate alarms | `duplicated(["event_time","source","code"])` | IDs are unique, but the content repeats |
| Reader offline | longest streak of consecutive cars missing SLR-2 | 49 cars in a row on 9 Sep |
| Lot id reused | lot used for more than 3× a normal lot size | `WS-260904-B` covers 1,785 cars (normal is ~300) |

**The run-id trick** (worth explaining):
`v.diff() != 0` is True whenever the value changes. `.cumsum()` turns that into a counter that only increases on a change, so every stretch of identical values gets the same number. Grouping by that number gives the run lengths.

---

## 3. `identity.py` – how each system names the same asset

There are two parts:
1. **Patterns per system**, from the plant overview and corrected by what the data shows.
2. **Six worked examples**, one per shop plus the relocated robot. Each row is a **regex search over the real files**, so the table is evidence, not copy-paste.

The section at the end, "Mapping rules this implies", is the bridge to Part C. Those rules become the rules-based matcher on Day 4. Examples:
- PI `R07` on L2 → `RB07`, station = ceil(7/2) = **ST04**, because there are two robots per station.
- Alarm `BIW/L2/S4/RB07` → replace separators → `S4` → `ST04` → `DDN1-BIW-L2-ST04-RB07`.
- **Exception:** `L1ST3_RB5` → `L2-ST06-RB12`, the relocated robot.

---

## 4. `problems.py` – the hidden production problems

### The evidence chain (the core idea of the whole assignment)
```
sensor anomaly window → VINs that passed that equipment in the window → their defects
```
This is the chain the knowledge graph will answer in one query on Day 7. Today we do it with pandas, to prove the problems are real.

### Lift: the key number
```
lift = (defect rate of exposed VINs) / (defect rate of all other VINs)
```
A lift of 1 means no relationship. "All" means every defect of that type is inside the window.

### Results
| # | Problem | Evidence | Verdict |
|---|---|---|---|
| 1 | PL1 die change 2 Sep 09:35 → tonnage +19 % | 28/28 panel splits are on cars using batches pressed in that window | Real (shows up a day later via genealogy) |
| 2 | Nutrunner TC14 transducer offset (–12 Nm) | 37 cars never re-hit = 37 audit torque defects | Real, safety-relevant |
| 3 | Robot L2 R07 weld current 9.96 → 7.96 kA | 101 of 107 cold welds, lift 174× | Real (gradual drift) |
| 4 | Door-seal lot `WS-260904-B` | 85/85 front-door leaks | Real, but the **lot id is unreliable** (see below) |
| 5 | Sealer SR03 heater band failed | 36/37 roof-ditch leaks; reader offline, so VINs were inferred | Real |
| 6 | Booth B humidifier valve stuck open | 7/7 craters, plus a flood of ~250 alarms | Real |
| 7 | Oven 2 zone 3 at +27 °C for 89 min | 0 extra defects; the manual says it's inside the bake window | **False quality alarm** |
| 8 | AHU TC1 fan bearing vibration rising | WO: bearing replaced 13 Sep | Real, caught before failure |
| 9 | E-coat TT-301 frozen | WO: transmitter reset | Data problem, not process |

### Three subtle points to raise in the interview
1. **Two water-leak causes overlap in time.** Separate them by **defect location**, not date: WL-104 is the front door upper edge (the seal), WL-101 is the roof ditch (sealer cell 2, per drawing DWG-PNT-SL-201).
2. **The lot id lies.** `WS-260904-B` was fitted on 4 Sep (293 cars, 0 leaks) and again on 8–10 Sep (1,492 cars, 85 leaks). Lots 0908–0910 never appear. The scanner was probably not updated, so **recall scope = lot id + fitting time**, otherwise you recall 293 good cars. This connects to interview Q3, the cost of a wrong link in a recall.
3. **The reader went offline exactly when the sealer failed.** The at-risk cars have no SLR-2 read. `vins_at(..., infer_from=[...])` estimates their time from the nearest station that did read them plus the median travel time. That's a preview of Part C6.

### Honest limitations (say these, don't hide them)
- 6 cold welds and 1 roof-ditch leak fall outside the windows. That's either background rate or threshold choice. I did **not** tune thresholds to make them disappear, because that would be overfitting.
- The 42 °C / 9.5 kA / 75 % thresholds come from the manuals and the overview. On Day 8 the anomaly detector will find windows without hand-set thresholds.
- The sealer window has a 5-minute margin because the nozzle temperature ramps up and down; it doesn't switch instantly.

---

## 5. Tests (`tests/test_day2.py`)
The tests lock in the key findings: outage = 45 min, the stuck sensor is found, alarm duplicates are found, 38 escaped NOKs, the weld-drift dates, missed reads get inferred, and the relocated robot resolves. If a refactor breaks one of them, `make test` fails.

## 6. Try this to learn
- In `problems.py`, change the weld threshold from `9.5` to `9.0` and re-run `make problems`. How do the window and the lift change?
- Remove `infer_from=[...]` in `sealer_cold_nozzle` and re-run. How many leaks become unexplained?
- Open `reports/02_data_quality.md` and, for 3 issues, find the evidence rows in the raw CSV yourself.

## Interview questions this day prepares
- **Q4** (why would real data score lower?): real data has more of these issues, and undocumented ones.
- **Q5** (a robot moved line): the relocated RB12 with its legacy tags.
- **Q3** (the cost of a wrong link in a recall): the lot-id reuse.
