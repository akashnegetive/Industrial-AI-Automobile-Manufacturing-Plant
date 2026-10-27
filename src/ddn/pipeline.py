"""Run the whole pipeline in order - the same on Windows, Mac and Linux.

    python -m ddn.pipeline            # all steps + tests
    python -m ddn.pipeline --no-tests

Used by run_all.ps1 / run_all.bat (Windows) and `make all` (Mac/Linux), so the
step list exists in exactly one place.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time

from .config import RAW, ROOT

# (module, what it produces) - order matters: later steps read earlier outputs.
STEPS = [
    ("ddn.profile", "Part B.1 dataset profiles"),
    ("ddn.quality", "Part B.2 data-quality report"),
    ("ddn.identity", "Part B.3 identity schemes"),
    ("ddn.problems", "Part B.4 production problems"),
    ("ddn.ontology", "Part D ontology check + docs"),
    ("ddn.tags", "Part C1 staging tables"),
    ("ddn.evaluate", "Part C rules baseline"),
    ("ddn.match_ml", "Part C ML matcher"),
    ("ddn.documents", "Part C5 drawings (incl. OCR) and manuals"),
    ("ddn.workorders", "Part C4 work-order failure modes (spaCy)"),
    ("ddn.context", "MES stations, feeds edges, alarm sources"),
    ("ddn.trace", "Part C6 VIN traceability"),
]

DATA_FILES = [
    "assets_cmms_export.csv", "historian_tag_list.csv", "timeseries_1min.csv.gz", "vehicles.csv",
    "mes_vehicle_passages.csv.gz", "mes_station_master.csv", "torque_results.csv.gz",
    "part_lot_genealogy.csv.gz", "press_panel_batches.csv", "quality_defects.csv",
    "maintenance_work_orders.csv", "alarms_andon_events.csv", "labels_tag_to_asset_TRAIN.csv",
    "labels_workorder_to_asset_TRAIN.csv",
]


def check_data() -> None:
    missing = [f for f in DATA_FILES if not (RAW / f).exists()]
    if missing:
        sys.exit(f"Missing {len(missing)} data file(s) in {RAW}:\n  " + "\n  ".join(missing)
                 + "\nCopy the data/ folder of Plant_DDN01_Candidate_Pack.zip into data/raw/.")


def main() -> None:
    check_data()
    start = time.time()
    for n, (module, label) in enumerate(STEPS, 1):
        print(f"\n[{n}/{len(STEPS)}] {label}  ({module})", flush=True)
        importlib.import_module(module).main()
    print(f"\nAll {len(STEPS)} steps done in {time.time() - start:.0f} s. Reports are in {ROOT / 'reports'}.")
    if "--no-tests" not in sys.argv:
        print("\nRunning tests ...", flush=True)
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


if __name__ == "__main__":
    main()
