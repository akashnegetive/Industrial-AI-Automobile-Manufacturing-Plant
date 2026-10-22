"""Loaders: read each raw file with the right types.

Why a loader module?
- Every later step (profiling, matching, graph) reads the same files. If types
  are fixed in one place, everything downstream agrees.
- Two typing traps in this pack:
  1. SAP equipment numbers are IDs, not numbers. pandas reads a column with
     blanks as float, so 10006783 becomes "10006783.0" and stops joining.
     We force them to string.
  2. Timestamps must be parsed as datetimes, otherwise time windows and
     sorting silently compare text.
"""
from __future__ import annotations

import pandas as pd

from .config import RAW

# file name -> (timestamp columns, columns that are IDs and must stay text)
SPECS: dict[str, tuple[list[str], list[str]]] = {
    "assets_cmms_export.csv": (["install_date"], ["cmms_equipment_no"]),
    "historian_tag_list.csv": ([], []),
    "timeseries_1min.csv.gz": (["timestamp"], []),
    "vehicles.csv": (["body_start_at"], []),
    "mes_vehicle_passages.csv.gz": (["passed_at"], []),
    "mes_station_master.csv": ([], []),
    "torque_results.csv.gz": (["timestamp"], ["result_id"]),
    "part_lot_genealogy.csv.gz": (["fitted_at"], []),
    "press_panel_batches.csv": (["produced_from", "produced_to"], []),
    "quality_defects.csv": (["detected_at"], []),
    "maintenance_work_orders.csv": (["created_at", "closed_at"], ["wo_number", "equipment_no"]),
    "alarms_andon_events.csv": (["event_time"], []),
    "labels_tag_to_asset_TRAIN.csv": ([], []),
    "labels_workorder_to_asset_TRAIN.csv": ([], ["wo_number"]),
}


def _clean_id(s: pd.Series) -> pd.Series:
    """'10006783.0' -> '10006783'; NaN stays missing."""
    return s.astype("string").str.replace(r"\.0$", "", regex=True).str.strip()


def load(name: str) -> pd.DataFrame:
    """Load one raw file by its file name, e.g. load('vehicles.csv')."""
    dates, ids = SPECS[name]
    df = pd.read_csv(RAW / name, dtype={c: "string" for c in ids}, low_memory=False)
    for c in ids:
        df[c] = _clean_id(df[c])
    for c in dates:
        # errors="coerce": a malformed timestamp becomes NaT instead of crashing,
        # and the data-quality report counts the NaTs.
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def load_all() -> dict[str, pd.DataFrame]:
    return {name: load(name) for name in SPECS}
