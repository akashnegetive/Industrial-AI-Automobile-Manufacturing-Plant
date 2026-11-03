"""Predictions for the evaluator's hidden test set (Part C is scored against it).

Writes outputs/predictions_tag_to_asset.csv and outputs/predictions_workorder_to_asset.csv in the same
format as the TRAIN label files (record, functional_location), plus how sure we are:

    confidence  ML score of the chosen asset (0-1)
    band        auto_accept (goes into the graph) | review (waits for an engineer) | backlog
    method      ml | engineer (an engineer approved or corrected it in the review screen)
    in_train    the record is in the TRAIN labels - leave it out when scoring

Every record gets its best prediction, including the review band, so recall can be measured; filter on
band == 'auto_accept' to score only what enters the graph without a person.

Run:  python -m ddn.export
"""
from __future__ import annotations

import pandas as pd

from .config import ROOT, STAGING
from .load import load
from .review import engineer_labels, rejected

OUT = ROOT / "outputs"
SOURCES = [  # (links file, key, train labels, review kind, output name)
    ("links_tag_name.parquet", "tag_name", "labels_tag_to_asset_TRAIN.csv", "tag", "predictions_tag_to_asset.csv"),
    ("links_wo_number.parquet", "wo_number", "labels_workorder_to_asset_TRAIN.csv", "workorder",
     "predictions_workorder_to_asset.csv"),
]


def predictions(links_file: str, key: str, train_file: str, kind: str) -> pd.DataFrame:
    p = pd.read_parquet(STAGING / links_file)[[key, "functional_location", "confidence", "band", "method"]].copy()
    eng = engineer_labels(kind)
    hit = p[key].isin(eng)
    p.loc[hit, "functional_location"] = p.loc[hit, key].map(eng)
    p.loc[hit, ["confidence", "band", "method"]] = [1.0, "auto_accept", "engineer"]
    p.loc[p[key].isin(rejected(kind)) & ~hit, "band"] = "backlog"      # engineer said no: not linked
    p["in_train"] = p[key].isin(set(load(train_file)[key]))
    p["confidence"] = p.confidence.round(4)
    return p.sort_values(key).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for links, key, train, kind, name in SOURCES:
        p = predictions(links, key, train, kind)
        p.to_csv(OUT / name, index=False)
        test = p[~p.in_train]
        print(f"{name}: {len(p):,} records, {len(test):,} not in TRAIN "
              f"({(test.band == 'auto_accept').mean():.1%} auto-accepted)")


if __name__ == "__main__":
    main()
