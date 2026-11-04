"""Part E1 - anomaly detection linked to context.

No hand-set limits: every signal is compared with its OWN recent behaviour.

Detectors
  1. Robust rolling z-score (main). Baseline = rolling 3-day median and MAD of the signal
     while producing (Sundays and idle values excluded), LAGGED so the recent past cannot
     contaminate its own baseline. Two horizons:
        fast: 12 h lag  - sudden events (die set-up, cold nozzle, humidity, oven)
        slow: 1 day lag - gradual degradation (bearing vibration)
     Alarm with hysteresis: starts at |z| > 6, continues while |z| > 3, gaps < 60 min merged,
     at least 10 minutes above 6.
  2. Flat-line: the same value for >= 60 minutes while producing = stuck sensor.
  3. Torque drift: the same z-score on each tool's deviation from its window centre (10-min bins).
  4. Isolation Forest per tag: run only as a comparison (see report), not as the alarm.

Context (why the graph matters)
  tag -> equipment (approved tag links) -> vehicles exposed in the window
  (processedBy edges, or the station the equipment belongs to / conditions, or press batches),
  -> their defect rate vs. all other vehicles, -> maintenance work orders on the same equipment.

Judgement (stated per event, with its reason)
  true_positive_quality   exposed vehicles show a defect at >= 5x the normal rate (>= 3 cases)
  true_positive_equipment no quality impact, but a maintenance WO on the equipment confirms it
  sensor_fault            flat-lined signal: data problem, not process problem
  false_alarm             real deviation, no quality impact and within documented tolerance,
                          or nothing confirms it

Run:  python -m ddn.anomaly     (writes data/staging/anomalies.parquet, anomaly_vins.parquet,
                                  reports/13_anomalies.md; the graph loader adds them to Neo4j)
"""
from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import REPORTS, STAGING
from .load import load
from .review import engineer_labels

warnings.filterwarnings("ignore", category=RuntimeWarning)
Z_HI, Z_LO, MIN_MINUTES = 6.0, 3.0, 10
LIFT_MIN, CASES_MIN = 5.0, 3


# ----------------------------------------------------------------- detectors
def robust_z(s: pd.Series, active: pd.Series | None = None, lag: str = "12h", win: str = "3D", minp: int = 360,
             smooth: str = "10min", smin: int = 5) -> pd.Series:
    """z = (x - lagged rolling median) / (1.4826 * lagged rolling MAD), smoothed by a rolling median.
    1.4826 * MAD equals the standard deviation for normal data, but outliers barely move it."""
    producing = s.index.day_of_week != 6                     # Sundays: no production
    x = s.where(producing & (active if active is not None else True))
    med = x.rolling(win, min_periods=minp).median()
    mad = (x - med).abs().rolling(win, min_periods=minp).median()
    ref = med.shift(freq=lag).reindex(s.index, method="ffill")
    scale = mad.shift(freq=lag).reindex(s.index, method="ffill")
    return ((x - ref) / (1.4826 * scale.clip(lower=1e-6))).rolling(smooth, min_periods=smin).median()


def alarm_windows(z: pd.Series, min_points: int = MIN_MINUTES, gap: str = "60min") -> list[dict]:
    """Hysteresis: an event is a stretch where |z| > Z_LO that contains >= min_points with |z| > Z_HI."""
    lo = z.index[z.abs() > Z_LO]
    if len(lo) == 0:
        return []
    out = []
    groups = (lo.to_series().diff() > pd.Timedelta(gap)).cumsum()
    for _, g in lo.to_series().groupby(groups):
        seg = z.loc[g.min():g.max()]
        if (seg.abs() > Z_HI).sum() >= min_points:
            peak = seg.abs().idxmax()
            out.append({"start": g.min(), "end": g.max(), "peak_z": round(float(seg.abs().max()), 1),
                        "direction": "high" if seg[peak] > 0 else "low"})
    return out


def minute_series(ts: pd.DataFrame, tag: str) -> tuple[pd.Series, pd.Series | None]:
    s = ts[ts.tag_name == tag].set_index("timestamp").value.sort_index().resample("1min").mean()
    level = s[s.index.day_of_week != 6].quantile(0.95)
    # 'running' values only: weld current, flow, tonnage... drop to ~0 between cycles
    active = s.abs() > 0.2 * abs(level) if level else None
    return s, active


def detect_signals(ts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tag in sorted(ts.tag_name.unique()):
        s, active = minute_series(ts, tag)
        fast = alarm_windows(robust_z(s, active, lag="12h"))
        rows += [{"signal": tag, "detector": "zscore_fast", **w} for w in fast]
        for w in alarm_windows(robust_z(s, active, lag="1D")):
            if not any(w["start"] <= f["end"] and w["end"] >= f["start"] for f in fast):
                rows.append({"signal": tag, "detector": "zscore_slow", **w})
        v = s.dropna()
        run = (v.diff() != 0).cumsum()
        size = v.groupby(run).transform("size")
        stuck = v[(size >= 60) & (v.index.day_of_week != 6) & ((active.reindex(v.index)) if active is not None else True)]
        for _, g in stuck.groupby(run.reindex(stuck.index)):
            rows.append({"signal": tag, "detector": "flatline", "start": g.index.min(), "end": g.index.max(),
                         "peak_z": None, "direction": f"flat at {g.iloc[0]:.2f}"})
    return pd.DataFrame(rows)


def detect_torque() -> pd.DataFrame:
    tq = load("torque_results.csv.gz")
    t1 = tq[(tq.attempt == 1) & tq.tool_id.str.startswith("TC")]
    rows = []
    for tool, g in t1.groupby("tool_id"):
        dev = (g.torque_nm - (g.torque_min + g.torque_max) / 2).groupby(g.timestamp.dt.floor("10min")).mean()
        z = robust_z(dev.resample("10min").mean(), minp=36, smooth="60min", smin=3)
        rows += [{"signal": f"{tool} torque", "detector": "torque_zscore", "tool": tool, **w}
                 for w in alarm_windows(z, min_points=2)]
    return pd.DataFrame(rows)


def isolation_forest(ts: pd.DataFrame, contamination: float = 0.002) -> pd.DataFrame:
    """Comparison only. Note: contamination=0.2 % means the model assumes every signal is anomalous
    0.2 % of the time, so it always flags something, even on a healthy signal."""
    rows = []
    for tag in sorted(ts.tag_name.unique()):
        s, active = minute_series(ts, tag)
        x = s.where((s.index.day_of_week != 6) & (active if active is not None else True))
        f = pd.DataFrame({"v": x, "m30": x.rolling("30min", min_periods=10).mean(),
                          "s30": x.rolling("30min", min_periods=10).std()}).dropna()
        if len(f) < 1000:
            continue
        flag = IsolationForest(n_estimators=200, contamination=contamination, random_state=7).fit_predict(f) == -1
        idx = f.index[flag]
        if len(idx) == 0:
            continue
        grp = (idx.to_series().diff() > pd.Timedelta("30min")).cumsum()
        for _, g in idx.to_series().groupby(grp):
            if len(g) >= MIN_MINUTES:
                rows.append({"signal": tag, "start": g.min(), "end": g.max(), "flagged_minutes": len(g)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- context
class Context:
    """Everything needed to go from a signal to equipment, vehicles, defects and work orders."""

    def __init__(self):
        links = pd.read_parquet(STAGING / "links_tag_name.parquet")
        links = links[links.band == "auto_accept"].set_index("tag_name").functional_location.to_dict()
        links.update(engineer_labels("tag"))
        self.tag_fl = links
        self.assets = pd.read_parquet(STAGING / "assets.parquet").set_index("functional_location")
        self.stations = pd.read_parquet(STAGING / "stations.parquet")
        self.fl_mes = dict(zip(self.stations.fl, self.stations.mes_station))
        self.feeds = pd.read_parquet(STAGING / "feeds.parquet")
        self.passages = pd.read_parquet(STAGING / "passages_full.parquet")
        self.processed = pd.read_parquet(STAGING / "processed_by.parquet")
        self.part_lots = pd.read_parquet(STAGING / "part_lots.parquet")
        self.defects = load("quality_defects.csv")
        self.n_vins = load("vehicles.csv").vin.nunique()
        wo_eng = engineer_labels("workorder")
        self.wos = pd.read_parquet(STAGING / "wo_failure_modes.parquet").merge(
            load("maintenance_work_orders.csv")[["wo_number", "created_at", "short_text", "long_text"]], on="wo_number")
        # same policy as the graph: approved links (auto or engineer); review-band links are shown as pending.
        # Backlog links are kept as candidates too: an anomaly is exactly the context that makes an unlikely
        # link worth a look, and review.build_queue pulls such work orders into the review queue.
        self.wos["functional_location"] = self.wos.wo_number.map(wo_eng).fillna(self.wos.functional_location)
        self.wos["link_status"] = np.where(self.wos.wo_number.isin(wo_eng), "engineer",
                                           np.where(self.wos.band == "auto_accept", "approved",
                                                    np.where(self.wos.band == "review", "pending review", "backlog")))
        self.tools = pd.read_parquet(STAGING / "tools.parquet").set_index("tool_id")

    def ancestors(self, fl: str) -> list[str]:
        out, cur = [], fl
        while isinstance(cur, str) and cur in self.assets.index:
            out.append(cur)
            cur = self.assets.at[cur, "parent_fl"]
        return out

    def exposed(self, fl: str, start, end) -> tuple[set[str], str]:
        """Vehicles exposed to an equipment's anomaly window, and how that was decided."""
        pb = self.processed[(self.processed.fl == fl) & (self.processed.start <= end) & (self.processed.end >= start)]
        if len(pb):
            return set(pb.vin), "processedBy (equipment touched the car)"
        for a in self.ancestors(fl):
            sup = self.feeds[(self.feeds.from_fl == a) & (self.feeds.relation == "supplies")]
            if len(sup):                    # press line: panels pressed in the window, fitted ~1 day later
                lots = self.part_lots[(self.part_lots.produced_from <= end) & (self.part_lots.produced_to >= start)
                                      & (self.part_lots.press_line == a.split("-")[-1])]
                return set(lots.vin), f"press batches produced in the window ({', '.join(sorted(lots.lot_id.unique()))})"
            cond = self.feeds[(self.feeds.from_fl == a) & (self.feeds.relation == "conditions")]
            target = cond.to_fl.iloc[0] if len(cond) else (a if a in self.fl_mes else None)
            if target:
                mes = self.fl_mes[target]
                p = self.passages[(self.passages.mes_station == mes) & self.passages.passed_at.between(start, end)]
                how = "conditions " if len(cond) else ""
                return set(p.vin), f"{how}station {mes}: cars that passed during the window"
        return set(), "no vehicle path (utility / plant-wide)"

    def defect_lift(self, vins: set[str]) -> dict:
        """The defect code most over-represented among exposed vehicles."""
        if not vins:
            return {}
        best = {}
        for code, g in self.defects.groupby("defect_code"):
            inside = g.vin.isin(vins).sum()
            outside = g.vin.nunique() - g[g.vin.isin(vins)].vin.nunique()
            rate_in = inside / len(vins)
            rate_out = outside / max(self.n_vins - len(vins), 1)
            lift = rate_in / rate_out if rate_out else (np.inf if inside else 0)
            if inside >= CASES_MIN and lift > best.get("lift", 0):
                best = {"defect_code": code, "defect_desc": g.defect_desc.mode()[0], "cases": int(inside),
                        "lift": float(lift), "vins_with_defect": set(g[g.vin.isin(vins)].vin)}
        return best

    # failure modes that fit an anomaly's direction (ISO 14224 codes from ddn.workorders)
    EXPECTED_MODES = {"low": {"LOO", "PDE"}, "high": {"HIO", "OHE", "PDE", "VIB", "NOI", "FTC"}, "flat": {"AIR"}}

    def confirming_wo(self, fl: str, start, end, direction: str = "") -> dict:
        """Repair or calibration WO on the equipment (or parent/children) from 1 day before to 3 days after.
        Prefer a WO whose failure mode fits the anomaly (low torque -> PDE/LOO, vibration -> VIB/NOI, ...)."""
        fam = set(self.ancestors(fl)[:2]) | set(self.assets.index[self.assets.parent_fl == fl])
        w = self.wos[self.wos.functional_location.isin(fam) & self.wos.created_at.between(
            start - pd.Timedelta("1D"), end + pd.Timedelta("3D")) & self.wos.wo_type.isin(["CM", "CAL"])].copy()
        if w.empty:
            return {}
        key = "flat" if direction.startswith("flat") else direction
        w["fits"] = w.iso14224.isin(self.EXPECTED_MODES.get(key, set()))
        r = w.sort_values(["fits", "created_at"], ascending=[False, True]).iloc[0]
        return {"wo_number": r.wo_number, "wo_text": r.short_text, "wo_failure_mode": r.iso14224,
                "wo_link": r.link_status}


def oven_within_bake_window(signal_values: pd.Series, start, end, setpoint_c: float = 150.0) -> bool:
    """MAN-TLN-GM2: an over-temperature under 2 h and under +30 C is normally inside the bake window."""
    return (end - start) <= pd.Timedelta("2h") and signal_values.max() - setpoint_c < 30


def judge(ev: dict, lift: dict, wo: dict) -> tuple[str, str]:
    if ev["detector"] == "flatline":
        return "sensor_fault", ("signal flat-lined while the process was running: a data problem, not a process "
                                "problem" + (f"; confirmed by WO {wo['wo_number']} ({wo['wo_text']})" if wo else ""))
    if lift and lift["lift"] >= LIFT_MIN:
        rate = ("only on exposed vehicles" if np.isinf(lift["lift"]) else f"at {lift['lift']:.0f}x the normal rate")
        return "true_positive_quality", (f"exposed vehicles have {lift['defect_desc']} ({lift['defect_code']}) "
                                         f"{rate} ({lift['cases']} cases)"
                                         + (f"; WO {wo['wo_number']}: {wo['wo_text']}" if wo else ""))
    if ev.get("bake_ok"):
        return "false_alarm", ("real over-temperature, but under 2 h and under +30 C, i.e. inside the bake window "
                               "(MAN-TLN-GM2), and no extra paint defects on the cars in the oven"
                               + (f"; WO {wo['wo_number']} tuned the burner" if wo else ""))
    if wo:
        return "true_positive_equipment", (f"no quality impact, but WO {wo['wo_number']} confirms an equipment problem "
                                           f"({wo['wo_text']}, failure mode {wo['wo_failure_mode']})")
    return "false_alarm", "no quality impact and no maintenance record confirms it"


# -------------------------------------------------------------------- runner
def run() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ts = pd.read_parquet(STAGING / "timeseries")
    ts["tag_name"] = ts.tag_name.astype(str)
    ctx = Context()
    events = pd.concat([detect_signals(ts), detect_torque()], ignore_index=True).sort_values("start")
    rows, exposure = [], []
    for i, ev in enumerate(events.to_dict("records"), 1):
        if ev["detector"] == "torque_zscore":
            fl = ctx.tools.at[ev["tool"], "equipment_fl"]
            tag = None
        else:
            tag, fl = ev["signal"], ctx.tag_fl.get(ev["signal"])
        aid = f"AN-{i:03d}"
        vins, how = ctx.exposed(fl, ev["start"], ev["end"]) if fl else (set(), "signal not linked to an asset")
        if ev["detector"] == "torque_zscore":
            tq = load("torque_results.csv.gz")
            bad = tq[(tq.tool_id == ev["tool"]) & tq.timestamp.between(ev["start"], ev["end"])]
            vins, how = set(bad.vin), "torque results from this tool in the window"
        lift = ctx.defect_lift(vins)
        wo = ctx.confirming_wo(fl, ev["start"], ev["end"], str(ev.get("direction") or "")) if fl else {}
        if tag and re.search(r"(Oven|OVN|Ovn)\d.*-Temp$", tag):
            vals = ts[(ts.tag_name == tag) & ts.timestamp.between(ev["start"], ev["end"])].value
            ev["bake_ok"] = oven_within_bake_window(vals, ev["start"], ev["end"])
        verdict, reason = judge(ev, lift, wo)
        rows.append({"anomaly_id": aid, "detector": ev["detector"], "signal": ev["signal"], "tag": tag,
                     "functional_location": fl, "start": ev["start"], "end": ev["end"],
                     "minutes": int((ev["end"] - ev["start"]).total_seconds() // 60) + 1,
                     "peak_z": ev.get("peak_z"), "direction": ev.get("direction"), "vehicles_exposed": len(vins),
                     "exposure_basis": how, "top_defect": lift.get("defect_code"), "defect_cases": lift.get("cases"),
                     "defect_lift": round(lift["lift"], 1) if lift else None, "confirming_wo": wo.get("wo_number"),
                     "wo_link": wo.get("wo_link"),
                     "judged": verdict, "reason": reason})
        caused = lift.get("vins_with_defect", set()) if verdict == "true_positive_quality" else set()
        exposure += [{"anomaly_id": aid, "vin": v, "has_top_defect": v in caused} for v in sorted(vins)]
    return pd.DataFrame(rows), pd.DataFrame(exposure), isolation_forest(ts)


def main() -> None:
    an, exp, iso = run()
    an.to_parquet(STAGING / "anomalies.parquet", index=False)
    exp.to_parquet(STAGING / "anomaly_vins.parquet", index=False)

    def overlaps(r):
        same = an[an.tag == r.signal]
        return bool(((same.start <= r.end) & (same.end >= r.start)).any())
    iso["matches_zscore_event"] = iso.apply(overlaps, axis=1) if len(iso) else []
    out = ["# Part E1 – Anomaly detection linked to context", "",
           "Generated by `python -m ddn.anomaly`. No hand-set limits: each signal is compared with its own lagged "
           "3-day median/MAD while producing (robust z-score), with hysteresis (start |z|>6, continue |z|>3, "
           "≥10 min). Fast horizon (12 h lag) for sudden events, slow horizon (1 day lag) for gradual drift; "
           "flat-line check for stuck sensors; the same z-score on each nutrunner's torque.", "",
           f"**{len(an)} events**: " + ", ".join(f"{k} {v}" for k, v in an.judged.value_counts().items()), "",
           "| ID | Detector | Signal | Equipment | Window | Peak z | Vehicles exposed | Top defect (lift) | WO | Verdict |",
           "|---|---|---|---|---|---:|---:|---|---|---|"]
    for r in an.itertuples():
        win = f"{r.start:%d %b %H:%M} → {r.end:%d %b %H:%M}"
        has_defect = isinstance(r.top_defect, str)          # NaN is truthy, so test the type, not truthiness
        lift = "every case" if has_defect and np.isinf(r.defect_lift) else f"{r.defect_lift:g}x"
        top = f"{r.top_defect} ({lift}, {int(r.defect_cases)} cases)" if has_defect else "—"
        wo_txt = ("—" if not isinstance(r.confirming_wo, str) else
                  r.confirming_wo + {"pending review": " (link pending review)",
                                     "backlog": " (link in backlog, sent to review)"}.get(r.wo_link, ""))
        out.append(f"| {r.anomaly_id} | {r.detector} | `{r.signal}` | `{r.functional_location}` | {win} | "
                   f"{'' if pd.isna(r.peak_z) else r.peak_z} | {r.vehicles_exposed:,} | {top} | "
                   f"{wo_txt} | **{r.judged}** |")
    out += ["", "## Reasons", ""]
    out += [f"- **{r.anomaly_id}** ({r.judged}): {r.reason}. Exposure: {r.exposure_basis}." for r in an.itertuples()]
    out += ["", "## Not detectable from signals", "",
            "- Door-seal lot WS-260904-B: no sensor sees a supplier part. It is found by the genealogy query (D5), "
            "which is the point of linking parts to vehicles.", "",
            "## Isolation Forest comparison", "",
            f"Per-tag Isolation Forest (contamination 0.2 %): {len(iso)} windows of ≥ 10 flagged minutes, "
            f"{int(iso.matches_zscore_event.sum()) if len(iso) else 0} overlap a z-score event, "
            f"{int((~iso.matches_zscore_event).sum()) if len(iso) else 0} do not.", "",
            "| Signal | Window | Flagged minutes | Matches a z-score event |", "|---|---|---:|---|"]
    out += [f"| `{r.signal}` | {r.start:%d %b %H:%M} → {r.end:%d %b %H:%M} | {r.flagged_minutes} | "
            f"{'yes' if r.matches_zscore_event else '**no**'} |" for r in iso.sort_values("start").itertuples()]
    out += ["", "Why the z-score is the alarm and Isolation Forest only a cross-check: the forest is told that 0.2 % of "
            "*every* signal is anomalous, so it always flags something (the unmatched windows above); it sees "
            "only short fragments of long events; it cannot see a stuck sensor (a constant value is 'normal'); and "
            "its score is hard to explain to a shift engineer, while 'z = 9: nine spreads above its own normal' is not.", ""]
    path = REPORTS / "13_anomalies.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"anomalies: {len(an)} events ({an.judged.value_counts().to_dict()}), {len(exp):,} vehicle exposures; "
          f"isolation forest {len(iso)} windows -> {path}")


if __name__ == "__main__":
    main()
