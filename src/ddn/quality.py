"""Part B.2 - data-quality report.

Each check is a small function that looks at one dataset and returns Issue
objects with a count and concrete evidence (example rows). Keeping every check
separate means each one can be explained, tested and re-run on its own.

Run:  python -m ddn.quality      (writes reports/02_data_quality.md)
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable

import pandas as pd
from pydantic import BaseModel

from .config import REPORTS
from .load import load


class Issue(BaseModel):
    """One data-quality finding. pydantic validates the fields for us."""
    dataset: str
    check: str
    severity: str            # High = breaks linking/analysis, Medium = misleads, Low = cosmetic
    count: int
    evidence: list[str]      # a few concrete examples a reviewer can verify
    impact: str              # why it matters for the pipeline
    documented: bool = False  # listed in the data dictionary already?


def _ex(values, n: int = 5) -> list[str]:
    return [str(v) for v in list(values)[:n]]


# ---------------------------------------------------------------- assets ----
def check_assets(a: pd.DataFrame) -> list[Issue]:
    out = []
    non_site = a[a.asset_type != "Site"]

    blank = non_site[non_site.parent_functional_location.isna()]
    out.append(Issue(dataset="assets", check="Missing parent functional location", severity="High",
                     count=len(blank), evidence=_ex(blank.functional_location), documented=True,
                     impact="Breaks the partOf hierarchy; repair by trimming the last FL segment."))

    # The FL is a path, so the parent *should* be the FL minus its last segment.
    # Dies contain hyphens inside their id (D-BSO-LH-03), so that rule fails for them.
    fl = set(a.functional_location)
    implied = non_site.functional_location.str.rsplit("-", n=1).str[0]
    bad = non_site[~implied.isin(fl)]
    out.append(Issue(dataset="assets", check="Equipment id contains the path separator '-'", severity="Medium",
                     count=len(bad), evidence=_ex(bad.functional_location),
                     impact="Naive split on '-' gives wrong parent/levels; parser must special-case dies."))

    # Typos: words in names that appear rarely and are close to a common word.
    words = Counter(w for n in a.name for w in re.findall(r"[A-Za-z]{3,}", n))
    from rapidfuzz import process, fuzz
    common = [w for w, c in words.items() if c >= 5]
    typos = []
    for w, c in words.items():
        if c <= 2:
            m = process.extractOne(w, common, scorer=fuzz.ratio)
            if m and 80 <= m[1] < 100:
                typos.append((w, m[0]))
    typo_rows = a[a.name.str.contains("|".join(rf"\b{w}\b" for w, _ in typos))] if typos else a.iloc[:0]
    out.append(Issue(dataset="assets", check="Misspelt asset names", severity="Medium",
                     count=len(typo_rows), documented=True,
                     evidence=[f"{r.functional_location}: '{r.name}'" for r in typo_rows.head(6).itertuples()]
                     + [f"{w} -> {c}" for w, c in typos[:6]],
                     impact="Lowers fuzzy-match scores against names; match on FL tokens, not names only."))

    dup = a[a.name.duplicated(keep=False)]
    out.append(Issue(dataset="assets", check="Same name on different assets", severity="High",
                     count=dup.name.nunique(), documented=True,
                     evidence=[f"'{n}' x{c}" for n, c in dup.name.value_counts().head(5).items()],
                     impact="'Robot 07' exists on L1, L2 and L3: a name alone can never identify the asset."))

    reloc = a[a.description.fillna("").str.contains("Relocated", case=False)]
    out.append(Issue(dataset="assets", check="Relocated equipment", severity="High",
                     count=len(reloc), evidence=[f"{r.functional_location}: {r.description}" for r in reloc.itertuples()],
                     impact="Historian tags keep the old controller name (DDN1_BIW_L1ST3_RB5_*): parsing the "
                            "tag gives the wrong robot. Needs a rule plus validity dates in the graph."))

    return out


# ------------------------------------------------------------------ tags ----
PATTERNS = {   # documented naming conventions from the plant overview
    "PI Historian": r"^DDN1_[A-Z]+_[A-Z0-9]+_[A-Z0-9]+_[A-Z0-9]+\.PV$",
    "WinCC SCADA": r"^PaintShop-[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+$",
    "S7 legacy OPC": r"^[A-Z]+\.[A-Z0-9]+\.[A-Z0-9]+\.[A-Z0-9]+$",
    "MES": r"^FA_[A-Z0-9]+_[A-Z0-9]+_[A-Z0-9]+$",
}


def check_tags(t: pd.DataFrame) -> list[Issue]:
    out = []
    bad = t[[not re.match(PATTERNS[s], n) for n, s in zip(t.tag_name, t.source_system)]]
    out.append(Issue(dataset="tags", check="Tag name breaks its system's naming convention (typos)",
                     severity="High", count=len(bad), evidence=_ex(bad.tag_name, 8), documented=True,
                     impact="Rule-based parser fails; needs fuzzy matching (DD1_, DN1_, F_AFN1_, misplaced '.')."))

    wincc_area = t[t.source_system == "WinCC SCADA"].tag_name.str.split("-").str[1]
    out.append(Issue(dataset="tags", check="Same WinCC area spelled several ways", severity="Medium",
                     count=wincc_area.nunique(), documented=True,
                     evidence=_ex(sorted(wincc_area.unique()), 10),
                     impact="Oven2 / OVN2 / Ovn02 must normalise to OV2 before matching."))

    for col, label in [("description", "Blank description"), ("engineering_unit", "Blank engineering unit")]:
        m = t[t[col].isna()]
        out.append(Issue(dataset="tags", check=label, severity="Medium", count=len(m),
                         evidence=[f"{s}: {m[m.source_system == s].shape[0]}" for s in m.source_system.unique()],
                         documented=True,
                         impact="Fewer features for the matcher; unit-vs-equipment check impossible for these."))

    degf = t[t.engineering_unit == "degF"]
    out.append(Issue(dataset="tags", check="Temperatures in deg F (rest of plant deg C)", severity="High",
                     count=len(degf), evidence=_ex(degf.tag_name), documented=True,
                     impact="Oven setpoint 150 C reads as ~302 F; must convert before thresholds or comparisons."))

    reloc = t[t.tag_name.str.contains("L1ST3_RB5")]
    out.append(Issue(dataset="tags", check="Legacy tag name of relocated robot", severity="High",
                     count=len(reloc), evidence=_ex(reloc.tag_name, 3) + _ex(reloc.description.dropna(), 2),
                     impact="Name says L1 ST03 R05, description and TRAIN labels say L2 ST06 RB12."))
    return out


# ------------------------------------------------------------ time series ----
def check_timeseries(ts: pd.DataFrame) -> list[Issue]:
    out = []
    full = pd.date_range(ts.timestamp.min().normalize(), ts.timestamp.max().ceil("D"), freq="min", inclusive="left")
    per_min = ts.groupby("timestamp").size().reindex(full, fill_value=0)
    empty = per_min[per_min == 0].index
    if len(empty):
        out.append(Issue(dataset="timeseries", check="Historian outage (all tags missing)", severity="High",
                         count=len(empty), documented=True,
                         evidence=[f"{empty.min()} -> {empty.max()} ({len(empty)} min, all 55 tags)"],
                         impact="Anomaly detectors must treat this as missing, not as a drop to zero."))

    expected = len(full) - len(empty)
    gaps = (expected - ts.groupby("tag_name").size()).sort_values(ascending=False)
    out.append(Issue(dataset="timeseries", check="Random missing minutes per tag (outside the outage)",
                     severity="Low", count=int(gaps.sum()), documented=True,
                     evidence=[f"{k}: {v} min" for k, v in gaps.head(4).items()],
                     impact="Use time-based rolling windows, not row counts."))

    # Stuck sensor: a long run of identical values on a signal that normally moves.
    for tag, s in ts.sort_values("timestamp").groupby("tag_name"):
        v = s.value.reset_index(drop=True)
        run_id = (v.diff() != 0).cumsum()
        runs = v.groupby(run_id).agg(["size", "first"])
        longest = runs["size"].max()
        if longest >= 60 and runs.loc[runs["size"].idxmax(), "first"] != 0:
            rows = s.iloc[(run_id == runs["size"].idxmax()).to_numpy()]
            flagged = (rows.quality == "Questionable").sum()
            out.append(Issue(dataset="timeseries", check="Stuck (flat-lined) sensor", severity="High",
                             count=int(longest), documented=True,
                             evidence=[f"{tag} = {rows.value.iloc[0]} from {rows.timestamp.min()} to "
                                       f"{rows.timestamp.max()}", f"only {flagged} of {len(rows)} marked Questionable"],
                             impact="Quality flag misses it; a flat-line detector is needed. WO 4102968 confirms."))

    q = ts[ts.quality == "Questionable"]
    out.append(Issue(dataset="timeseries", check="Questionable quality flags (scattered, not tied to faults)",
                     severity="Low", count=len(q),
                     evidence=[f"{len(q) / len(ts):.2%} of values, spread over all tags and days"],
                     impact="The quality column is not a reliable fault indicator."))

    idle = ts[(ts.timestamp.dt.day_of_week == 6) & ts.tag_name.str.contains("WELDCUR|FLOW")]
    out.append(Issue(dataset="timeseries", check="Idle-time values (Sundays ~0, small negatives)", severity="Low",
                     count=int((idle.value < 0).sum()), evidence=[f"min {idle.value.min()} on Sundays 6/13 Sep"],
                     impact="Not a fault: filter to production time before computing baselines."))
    return out


# --------------------------------------------------------- MES / product ----
def check_mes(v: pd.DataFrame, p: pd.DataFrame, st: pd.DataFrame) -> list[Issue]:
    out = []
    out.append(Issue(dataset="vehicles", check="VIN is 16 characters (ISO 3779 requires 17)", severity="Medium",
                     count=int((v.vin.str.len() != 17).sum()), evidence=_ex(v.vin, 3),
                     impact="A VIN validator must not reject them; note it as a synthetic-data artefact."))

    booth = {"TC-1", "TC-2", "OV-1", "OV-2"}
    wrong_area = st[st.mes_station.str.startswith("OV") & (st.area != "PAINT")]
    out.append(Issue(dataset="mes_station_master", check="Topcoat ovens labelled area ASSY", severity="Low",
                     count=len(wrong_area), evidence=[f"{r.mes_station}: {r.area}" for r in wrong_area.itertuples()],
                     impact="Ovens are in the Paint Shop; mapping by area would misplace them."))

    fixed = [s for s in st.mes_station if s not in booth]
    have = pd.crosstab(p.vin, p.mes_station)
    miss = (have[fixed] == 0).stack()
    miss = miss[miss].reset_index()
    out.append(Issue(dataset="mes_vehicle_passages", check="Missing RFID reads", severity="High",
                     count=len(miss), documented=True,
                     evidence=[f"{len(miss) / (len(v) * len(fixed)):.2%} of expected fixed-route reads",
                               f"most at SLR-2: {(miss.mes_station == 'SLR-2').sum()}"],
                     impact="Must infer the passage from line order + takt and mark it inferred."))

    # Reader offline: consecutive vehicles missing the same station.
    order = p[p.mes_station == "SLR-1"].sort_values("passed_at")
    seq = order.vin.tolist()
    slr2 = set(p[p.mes_station == "SLR-2"].vin)
    run, best, start = 0, (0, None, None), None
    for vin, t in zip(seq, order.passed_at):
        if vin not in slr2:
            run, start = run + 1, start or t
            if run > best[0]:
                best = (run, start, t)
        else:
            run, start = 0, None
    out.append(Issue(dataset="mes_vehicle_passages", check="RFID reader offline (consecutive missed reads)",
                     severity="High", count=best[0], documented=True,
                     evidence=[f"RD-SLR-2 missed {best[0]} cars in a row, SLR-1 time {best[1]} -> {best[2]}"],
                     impact="Same window as sealer SR03 cold nozzle: the at-risk VINs have no SLR-2 read."))
    return out


def check_genealogy(g: pd.DataFrame) -> list[Issue]:
    """A supplier lot normally lasts one 12-hour half-day (A/B). Flag lots used far longer."""
    span = g.groupby(["part_no", "lot_id"]).agg(n=("vin", "size"), start=("fitted_at", "min"), end=("fitted_at", "max"))
    typical = span.groupby("part_no").n.median()
    long = span[span.n > 3 * span.index.get_level_values(0).map(typical)]
    return [Issue(dataset="part_lot_genealogy", check="Lot id reused far beyond a normal lot size", severity="High",
                  count=len(long),
                  evidence=[f"{p} {l}: {r.n} VINs, {r.start:%d %b %H:%M} -> {r.end:%d %b %H:%M}"
                            for (p, l), r in long.iterrows()],
                  impact="Lot id not updated at fitting: recall scope must use lot id + fitting time.")]


def check_torque(tq: pd.DataFrame) -> list[Issue]:
    out = []
    inside = tq.torque_nm.between(tq.torque_min, tq.torque_max)
    mism = tq[inside & (tq.status == "NOK")]
    out.append(Issue(dataset="torque_results", check="Status NOK although torque is on the window limit",
                     severity="Low", count=len(mism),
                     evidence=[f"{r.result_id} {r.joint_id} {r.torque_nm} Nm window {r.torque_min}-{r.torque_max}"
                               for r in mism.head(3).itertuples()],
                     impact="Boundary is exclusive in the controller; use the status field, not a recomputation."))

    first_nok = tq[(tq.attempt == 1) & (tq.status == "NOK")]
    rehit = tq[tq.attempt == 2][["vin", "joint_id"]].drop_duplicates()
    k = first_nok.merge(rehit, on=["vin", "joint_id"], how="left", indicator=True)
    no_rehit = k[k._merge == "left_only"]
    out.append(Issue(dataset="torque_results", check="NOK tightening with no re-hit recorded", severity="High",
                     count=len(no_rehit), evidence=_ex(no_rehit.vin + " " + no_rehit.joint_id),
                     impact="These cars left the line under-torqued; they match the audit 'Wheel nut torque low' defects."))
    out.append(Issue(dataset="torque_results", check="Re-hits come from HW-07 (not a TCnn channel)",
                     severity="Low", count=int((tq.tool_id == "HW-07").sum()), documented=True,
                     evidence=["tool_id HW-07, attempt 2"], impact="HW-07 is a hand wrench, not a nutrunner asset."))
    return out


def check_defects(d: pd.DataFrame) -> list[Issue]:
    multi = d.groupby("defect_code").defect_desc.unique()
    multi = multi[multi.str.len() > 1]
    same_desc = d.groupby("defect_desc").defect_code.unique()
    same_desc = same_desc[same_desc.str.len() > 1]
    return [
        Issue(dataset="quality_defects", check="One defect code, several descriptions", severity="Medium",
              count=len(multi), evidence=[f"{k}: {list(v)}" for k, v in multi.items()],
              impact="Group by defect_code, not description, when counting spikes."),
        Issue(dataset="quality_defects", check="One description, several codes", severity="Low",
              count=len(same_desc), evidence=[f"{k}: {list(v)}" for k, v in same_desc.items()],
              impact="WL-101 and WL-104 both 'Water leak': merge into one family."),
        Issue(dataset="quality_defects", check="Defects never reference equipment", severity="High",
              count=len(d), documented=True, evidence=_ex(d.inspection_point.unique()),
              impact="Root cause needs VIN -> passages -> station -> equipment at the right time."),
    ]


def check_workorders(wo: pd.DataFrame, a: pd.DataFrame, labels: pd.DataFrame) -> list[Issue]:
    eq = a.dropna(subset=["cmms_equipment_no"]).set_index("cmms_equipment_no").functional_location
    lab = labels.merge(wo, on="wo_number")
    lab = lab[lab.equipment_no.notna()].assign(eq_fl=lambda x: x.equipment_no.map(eq))
    wrong = lab[lab.eq_fl != lab.functional_location]
    water = wo[wo.short_text.str.contains("water leak", case=False) & wo.failure_code.notna()]
    leak_share = (water.failure_code == "LEAK").mean()
    hinglish = wo[wo.short_text.str.contains(r"\b(?:ka|nahi|raha|hai|kiya|aa)\b", case=False)]
    return [
        Issue(dataset="work_orders", check="Blank equipment number", severity="High",
              count=int(wo.equipment_no.isna().sum()), documented=True, evidence=_ex(wo[wo.equipment_no.isna()].short_text),
              impact="Asset must be inferred from free text."),
        Issue(dataset="work_orders", check="Equipment number points to the wrong asset (checked against TRAIN labels)",
              severity="High", count=len(wrong), documented=True,
              evidence=[f"WO {r.wo_number}: eq -> {r.eq_fl}, truth {r.functional_location} ('{r.short_text}')"
                        for r in wrong.head(3).itertuples()]
                       + [f"{len(wrong) / len(lab):.1%} of labelled WOs that have an equipment no."],
              impact="Exact-ID rule alone gives ~4% wrong links: always cross-check against the text."),
        Issue(dataset="work_orders", check="Hinglish shorthand in text", severity="Medium",
              count=len(hinglish), documented=True, evidence=_ex(hinglish.short_text),
              impact="Needs a custom vocabulary (nahi chal raha = not running, trip ho raha hai = tripping)."),
        Issue(dataset="work_orders", check="Nicknames instead of ids", severity="Medium",
              count=int(wo.short_text.str.contains(r"\b(?:R\d{1,2}|Rob \d+|robot no \d+|DC tool \d+|robo)\b",
                                                   case=False).sum()),
              documented=True, evidence=["R7", "Rob 07", "robot no 7 L3", "DC tool 14", "L2 ST03 robo"],
              impact="Line is often missing ('R7'): candidate generation must consider every line."),
        Issue(dataset="work_orders", check="Blank failure code", severity="Medium",
              count=int(wo.failure_code.isna().sum()), documented=True, evidence=["failure_code empty"],
              impact="Failure mode must be extracted from text and mapped to ISO 14224."),
        Issue(dataset="work_orders", check="SAP failure_code unrelated to the text", severity="High",
              count=int(wo.failure_code.notna().sum()),
              evidence=[f"'water leak' WOs coded LEAK: {leak_share:.0%} (6 codes -> random would be ~17 %)",
                        f"failure_code blank on {wo[wo.wo_type == 'CM'].failure_code.isna().mean():.0%} of CM WOs, "
                        "on every PM/CAL WO"],
              impact="Cannot be used as a label; failure modes must come from the text (ddn.workorders)."),
        Issue(dataset="work_orders", check="Long text almost always empty", severity="Low",
              count=int(wo.long_text.isna().sum()), evidence=[f"only {wo.long_text.notna().sum()} WOs have long text"],
              impact="The few long texts are the root-cause records for this fortnight's problems."),
    ]


def check_alarms(al: pd.DataFrame) -> list[Issue]:
    norm = al.source.str.replace(r"[._/\-]", "_", regex=True)
    seps = al.source.str.extract(r"([._/])")[0].value_counts()
    dup = al[al.duplicated(["event_time", "source", "code"], keep=False)]
    hourly = al.groupby(al.event_time.dt.floor("h")).size()
    flood = hourly[hourly > 4 * hourly.median()]
    top = al[al.event_time.dt.floor("h").isin(flood.index)].source.value_counts().head(1)
    short = al[al.source.str.contains(r"[/._]S\d[/._]")]
    return [
        Issue(dataset="alarms", check="Mixed separators in source path (count = distinct sources)", severity="High",
              count=int(norm.nunique()), documented=True,
              evidence=[f"'{k}': {v}" for k, v in seps.items()] + _ex(al.source.drop_duplicates().sample(4, random_state=1)),
              impact="Normalise separators before matching to functional locations."),
        Issue(dataset="alarms", check="Station abbreviated S3 instead of ST03", severity="Medium",
              count=len(short), evidence=_ex(short.source.unique()),
              impact="Normaliser must expand S<n> to ST0<n>."),
        Issue(dataset="alarms", check="Duplicate events (same time, source, code, new event_id)", severity="Medium",
              count=int(al.duplicated(["event_time", "source", "code"]).sum()), documented=True,
              evidence=_ex(dup.event_id, 4),
              impact="Unique-id check misses them; dedupe on content or counts are inflated ~3%."),
        Issue(dataset="alarms", check="Alarm flood", severity="Medium", count=int(flood.sum()), documented=True,
              evidence=[f"{h}: {n} events" for h, n in flood.items()] + [f"source {k}: {v}" for k, v in top.items()],
              impact="One root cause (TC2 humidifier) produces ~250 alarms; rank by source, not by count."),
    ]


CHECKS: list[Callable[[], list[Issue]]] = [
    lambda: check_assets(load("assets_cmms_export.csv")),
    lambda: check_tags(load("historian_tag_list.csv")),
    lambda: check_timeseries(load("timeseries_1min.csv.gz")),
    lambda: check_mes(load("vehicles.csv"), load("mes_vehicle_passages.csv.gz"), load("mes_station_master.csv")),
    lambda: check_genealogy(load("part_lot_genealogy.csv.gz")),
    lambda: check_torque(load("torque_results.csv.gz")),
    lambda: check_defects(load("quality_defects.csv")),
    lambda: check_workorders(load("maintenance_work_orders.csv"), load("assets_cmms_export.csv"),
                             load("labels_workorder_to_asset_TRAIN.csv")),
    lambda: check_alarms(load("alarms_andon_events.csv")),
]


def run_all() -> list[Issue]:
    return [issue for check in CHECKS for issue in check()]


def to_markdown(issues: list[Issue]) -> str:
    sev = {"High": 0, "Medium": 1, "Low": 2}
    n_new = sum(not i.documented for i in issues)
    out = ["# Part B.2 – Data-quality report", "",
           "Generated by `python -m ddn.quality`. Each issue has a count and evidence you can verify in the raw files.",
           f"{len(issues)} issues found; {n_new} of them are **not** listed in the data dictionary.", "",
           "| # | Dataset | Issue | Severity | Count | In dictionary? |", "|---:|---|---|---|---:|---|"]
    issues = sorted(issues, key=lambda i: (i.dataset, sev[i.severity]))
    for n, i in enumerate(issues, 1):
        out.append(f"| {n} | {i.dataset} | {i.check} | {i.severity} | {i.count:,} | {'yes' if i.documented else '**new**'} |")
    out += ["", "## Evidence and impact", ""]
    for n, i in enumerate(issues, 1):
        out += [f"### {n}. {i.dataset}: {i.check}", "",
                f"*Severity {i.severity}, count {i.count:,}.* **Impact:** {i.impact}", ""]
        out += [f"- `{e}`" for e in i.evidence] + [""]
    return "\n".join(out)


def main() -> None:
    issues = run_all()
    path = REPORTS / "02_data_quality.md"
    path.write_text(to_markdown(issues), encoding="utf-8")
    print(f"{len(issues)} issues -> {path}")


if __name__ == "__main__":
    main()
