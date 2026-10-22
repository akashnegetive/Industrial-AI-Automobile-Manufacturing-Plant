# Day 1 – What we built and why

## Folder structure
```
plant-ddn01-kg/
├── data/raw/          original pack files (never modified)
├── data/staging/      cleaned Parquet files (Day 2+)
├── src/ddn/           the Python package (all pipeline code)
│   ├── config.py      paths and plant constants
│   ├── load.py        one typed loader for every file
│   └── profile.py     Part B.1 dataset profiles
├── tests/             pytest tests
├── reports/           generated reports (Markdown)
├── docs/              guides, explanations, the original pack docs
└── Makefile           `make all` runs everything
```
**Why:** the assignment wants a repo that "runs end to end in one command". Separating `raw` from `staging` means we never damage the original data and can always re-run.

## `config.py`
Holds all paths in one place. `Path(__file__).resolve().parents[2]` means "two folders above this file", which is the project root. So the code works no matter where you run it from.

## `load.py` – the important lessons
1. **IDs must be strings.** `equipment_no` has blanks, so pandas stores it as a *float*, and `10006783` becomes `10006783.0`. Joining that to the asset table's `cmms_equipment_no` would silently fail. We read ID columns with `dtype="string"` and strip a trailing `.0`.
2. **Dates must be parsed.** `pd.to_datetime(..., errors="coerce")` turns bad values into `NaT` (missing) instead of crashing. The data-quality report will count them.
3. **One `SPECS` dictionary** describes every file, so adding a file is one line.

*Interview line:* "I centralised typing in one loader because ID-as-float is a classic silent join failure in SAP exports."

## `profile.py` – Part B.1
For each file it computes:
- **rows / columns**: size;
- **expected key + duplicate check**: does `defect_id` really identify one row?
- **exact duplicate rows**;
- **time coverage**: min → max of the main timestamp;
- **missing values per column**;
- **how the file identifies equipment**: this column is *hand-written* in `META`, because it is domain knowledge. The script prints example values to prove it.

### What the output already tells us
- All keys are unique, *but* the alarm file has ~3% duplicates with **different event IDs**. A naive check misses them. Day 2 detects them by (time, source, code).
- Passages, torque and defects run into **15 Sep morning**. These are cars started on 14 Sep that finish later, which is normal and not an error.
- Work orders cover **12 months**, while everything else covers 2 weeks. Older work orders are useful for training the matcher, not for problem-finding.
- `quality_defects` points at **inspection points, not equipment**. Linking defects back to the machine that caused them needs the VIN's route: VIN → passages → station → equipment. That is the whole value of the knowledge graph.

## How to run it yourself
```bash
cd plant-ddn01-kg
make setup      # first time only
make all        # profile + tests
```
Then open `reports/01_dataset_profile.md`.

## Try this to learn
- Change `META["quality_defects.csv"]["key"]` to `["vin"]` and re-run. Why are there duplicates now? (One car can have several defects.)
- In Python: `from ddn.load import load; load("historian_tag_list.csv").source_system.value_counts()`
