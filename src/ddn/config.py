"""Central place for file paths, so no other module hard-codes a path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # project root (…/plant-ddn01-kg)
RAW = ROOT / "data" / "raw"                 # untouched files from the candidate pack
STAGING = ROOT / "data" / "staging"         # cleaned, typed Parquet files
REPORTS = ROOT / "reports"

# Plant facts from 01_Plant_DDN01_Overview.pdf (used by checks later)
PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-15"   # exclusive end: data covers 1-14 Sep
TAKT_MIN = 2.4
