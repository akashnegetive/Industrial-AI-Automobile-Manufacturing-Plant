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
# Need a running Neo4j (docker compose up -d). Skipped with a message if it is not reachable.
GRAPH_STEPS = [
    ("ddn.graph", "Part D load the knowledge graph into Neo4j"),
    ("ddn.queries", "Part D the seven graph queries"),
]

DATA_FILES = [
    "assets_cmms_export.csv", "historian_tag_list.csv", "timeseries_1min.csv.gz", "vehicles.csv",
    "mes_vehicle_passages.csv.gz", "mes_station_master.csv", "torque_results.csv.gz",
    "part_lot_genealogy.csv.gz", "press_panel_batches.csv", "quality_defects.csv",
    "maintenance_work_orders.csv", "alarms_andon_events.csv", "labels_tag_to_asset_TRAIN.csv",
    "labels_workorder_to_asset_TRAIN.csv",
]


DOCS = ROOT / "docs" / "source_pack" / "documents"


def check_data() -> None:
    """Fail early with a clear message: the pack's data and PDFs are not in git, they must be copied in."""
    problems = []
    missing = [f for f in DATA_FILES if not (RAW / f).exists()]
    if missing:
        problems.append(f"Missing {len(missing)} data file(s) in {RAW}:\n  " + "\n  ".join(missing)
                        + "\n  -> copy the pack's data/ folder contents into data/raw/")
    n_dwg = len(list((DOCS / "drawings").glob("*.pdf")))
    n_man = len(list((DOCS / "manuals").glob("*.pdf")))
    if n_dwg < 7 or n_man < 6:
        problems.append(f"Found {n_dwg}/7 drawings and {n_man}/6 manuals in {DOCS}\n"
                        "  -> copy the pack's documents/ folder to docs/source_pack/documents/ "
                        "(so that docs/source_pack/documents/drawings and .../manuals exist)")
    if problems:
        sys.exit("\n\n".join(problems))


def main() -> None:
    check_data()
    from .graph import neo4j_available
    print("Checking Neo4j (bolt://localhost:7687) ...", flush=True)
    graph_ok = neo4j_available()
    if not graph_ok:
        print("Neo4j is not reachable - the 2 graph steps will be SKIPPED. Start it with `docker compose up -d` "
              "(Docker Desktop must be running) and run again.")
    steps = STEPS + (GRAPH_STEPS if graph_ok else [])
    start = time.time()
    for n, (module, label) in enumerate(steps, 1):
        print(f"\n[{n}/{len(steps)}] {label}  ({module})", flush=True)
        importlib.import_module(module).main()
    print(f"\nAll {len(steps)} steps done in {time.time() - start:.0f} s"
          + ("" if graph_ok else " (graph steps skipped)") + f". Reports are in {ROOT / 'reports'}.")
    if "--no-tests" not in sys.argv:
        print("\nRunning tests ...", flush=True)
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


if __name__ == "__main__":
    main()
