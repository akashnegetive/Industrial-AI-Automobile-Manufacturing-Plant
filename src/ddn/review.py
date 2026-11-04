"""Part C7 - confidence gate and engineer review.

    confidence >= auto threshold   -> auto-accept: edge enters the graph (status approved)
    review band                    -> this queue: an engineer approves, rejects or corrects
    below review threshold         -> backlog (data-quality queue), never enters the graph

Decisions are appended to data/review/decisions.csv (kept in git: they are labelled
data). They are reused twice:
    1. the graph loader turns approve/correct into edges with method=engineer, confidence 1.0
    2. the ML matcher adds them to its training labels (Cognite calls this "refit")

The review screen itself is apps/review_app.py (Streamlit).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .config import ROOT, STAGING

REVIEW_DIR = ROOT / "data" / "review"
DECISIONS = REVIEW_DIR / "decisions.csv"
DECISION_COLS = ["item_id", "kind", "record", "decision", "functional_location", "proposed_fl",
                 "reviewer", "decided_at", "comment"]
DOC_AUTO = 0.90          # document links at or above this enter the graph without review


def build_queue() -> pd.DataFrame:
    """Every link waiting for a person, with the context a reviewer needs to decide."""
    tags = pd.read_parquet(STAGING / "tags.parquet").set_index("tag_name")
    wos = pd.read_parquet(STAGING / "wo_failure_modes.parquet").set_index("wo_number")
    wo_text = pd.read_csv(ROOT / "data" / "raw" / "maintenance_work_orders.csv", dtype=str).set_index("wo_number")
    rows = []
    for r in pd.read_parquet(STAGING / "links_tag_name.parquet").query("band == 'review'").itertuples():
        t = tags.loc[r.tag_name]
        rows.append({"item_id": f"tag:{r.tag_name}", "kind": "tag", "record": r.tag_name,
                     "context": f"{t.description or '(no description)'} | unit {t.unit or '-'} | {t.source_system}",
                     "proposed_fl": r.functional_location, "confidence": round(r.confidence, 3)})
    an_file = STAGING / "anomalies.parquet"
    explains = set(pd.read_parquet(an_file).confirming_wo.dropna()) if an_file.exists() else set()
    wol = pd.read_parquet(STAGING / "links_wo_number.parquet")
    # review band, plus backlog work orders that explain a detected anomaly (pulled up for a human look)
    for r in wol[(wol.band == "review") | ((wol.band == "backlog") & wol.wo_number.isin(explains))].itertuples():
        w = wo_text.loc[r.wo_number]
        rows.append({"item_id": f"wo:{r.wo_number}", "kind": "workorder", "record": r.wo_number,
                     "context": ("[from backlog] " if r.band == "backlog" else "") +
                                f"{w.short_text} | {w.long_text if pd.notna(w.long_text) else ''} | "
                                f"eq no {w.equipment_no if pd.notna(w.equipment_no) else '-'} | {w.created_at[:10]}",
                     "proposed_fl": r.functional_location, "confidence": round(r.confidence, 3)})
    # Part E3: backlog records get link prediction's top 3 (graph-based second opinion) as a review item
    sug_file = STAGING / "link_suggestions.parquet"
    sug = pd.read_parquet(sug_file) if sug_file.exists() else pd.DataFrame(columns=["record", "to_review"])
    already = {r["record"] for r in rows}
    for r in sug[sug.to_review & ~sug.record.isin(already)].itertuples():
        text = (f"{tags.loc[r.record].description or '(no description)'}" if r.kind == "tag"
                else f"{wo_text.loc[r.record].short_text}")
        rows.append({"item_id": f"e3:{r.kind}:{r.record}", "kind": r.kind, "record": r.record,
                     "context": f"[suggested by link prediction] {text} | other suggestions: {r.e3_alternatives} | "
                                f"matcher's guess: {r.matcher_fl} ({r.matcher_conf:.3f}, backlog)",
                     "proposed_fl": r.e3_fl, "confidence": round(float(r.e3_score), 3)})
    hint = dict(zip(sug.record, sug.get("e3_fl", pd.Series(dtype=str))))
    for row in rows:
        if row["kind"] in ("tag", "workorder") and not row["item_id"].startswith("e3:") and row["record"] in hint \
                and hint[row["record"]] != row["proposed_fl"]:
            row["context"] += f" | link prediction suggests {hint[row['record']]}"
    docs = pd.read_parquet(STAGING / "doc_mentions.parquet")
    for r in docs[(docs.confidence < DOC_AUTO) & docs.target.notna()].itertuples():
        rows.append({"item_id": f"doc:{r.doc_id}:{r.page}:{r.label}:{r.target}", "kind": "document",
                     "record": f"{r.doc_id} p.{r.page} '{r.label}'",
                     "context": f"read by {r.method}" + (" (OCR text was corrected)" if r.method == "ocr_corrected" else ""),
                     "proposed_fl": r.target, "confidence": r.confidence})
    q = pd.DataFrame(rows)
    # Items that explain a detected anomaly (Part E1) come first: they matter most for root cause.
    q["explains_anomaly"] = (q.kind == "workorder") & q.record.isin(explains)
    return q.sort_values(["explains_anomaly", "kind", "confidence"], ascending=[False, True, True]).reset_index(drop=True)


def backlog() -> pd.DataFrame:
    """The data-quality queue: links scored below the review threshold, not shown for approval (a reviewer
    would mostly reject them). Fixing the source record (missing equipment number, vague text) is the cure."""
    out = []
    for kind, f, key in [("tag", "links_tag_name.parquet", "tag_name"), ("workorder", "links_wo_number.parquet", "wo_number")]:
        p = STAGING / f
        if p.exists():
            d = pd.read_parquet(p).query("band == 'backlog'")
            out.append(pd.DataFrame({"kind": kind, "record": d[key], "best_guess": d.functional_location,
                                     "confidence": d.confidence.round(3)}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["kind", "record", "best_guess", "confidence"])


def load_decisions() -> pd.DataFrame:
    if not DECISIONS.exists():
        return pd.DataFrame(columns=DECISION_COLS)
    d = pd.read_csv(DECISIONS, dtype=str)
    return d.drop_duplicates("item_id", keep="last")          # a later decision overrides an earlier one


def save_decision(item: dict, decision: str, functional_location: str | None, reviewer: str,
                  comment: str = "") -> None:
    if decision not in {"approve", "reject", "correct"}:
        raise ValueError(decision)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{
        "item_id": item["item_id"], "kind": item["kind"], "record": item["record"], "decision": decision,
        "functional_location": functional_location if decision != "reject" else "",
        "proposed_fl": item["proposed_fl"], "reviewer": reviewer,
        "decided_at": datetime.now().isoformat(timespec="seconds"), "comment": comment}])
    row.to_csv(DECISIONS, mode="a", header=not DECISIONS.exists(), index=False)


def pending(queue: pd.DataFrame | None = None) -> pd.DataFrame:
    queue = build_queue() if queue is None else queue
    return queue[~queue.item_id.isin(load_decisions().item_id)]


def engineer_labels(kind: str) -> dict[str, str]:
    """Approved / corrected decisions as training labels: record -> functional location."""
    d = load_decisions()
    d = d[(d.kind == kind) & d.decision.isin(["approve", "correct"])]
    return dict(zip(d.record, d.functional_location))


def rejected(kind: str) -> set[str]:
    d = load_decisions()
    return set(d[(d.kind == kind) & (d.decision == "reject")].record)
