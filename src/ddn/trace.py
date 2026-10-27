"""Part C6 - VIN traceability: stations, equipment, torque, parts and lots per vehicle.

Missed RFID reads (~2 % at random, plus reader RD-SLR-2 offline on 9 Sep) are filled
from the line sequence: a car's time at a station it was not read at is interpolated
between the neighbouring stations it *was* read at, using the typical travel time
between stations (median offset from body start). Filled passages are flagged
inferred=True. The method is validated by hiding real reads and re-estimating them.

processedBy (VIN -> equipment) is materialised only for equipment that touches the
car (ontology): weld robots at body stations, sealer robots and their dispensers,
paint robots in the booth the car went through, and the nutrunner that actually
tightened each joint (from the torque results, not inferred).

Run:  python -m ddn.trace     (writes data/staging/passages_full.parquet, processed_by.parquet,
                                tools.parquet, part_lots.parquet, reports/10_vin_traceability.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import REPORTS, STAGING, TAKT_MIN
from .load import load

BOOTHS = ["TC-1", "TC-2", "OV-1", "OV-2"]


def minutes_matrix(p: pd.DataFrame, v: pd.DataFrame, route: list[str]) -> pd.DataFrame:
    """VIN x station matrix of minutes after body start (NaN = no read)."""
    m = p.merge(v[["vin", "body_start_at"]], on="vin")
    m["min"] = (m.passed_at - m.body_start_at).dt.total_seconds() / 60
    return m.pivot(index="vin", columns="mes_station", values="min").reindex(columns=route)


def fill_missing(M: pd.DataFrame, offsets: pd.Series) -> pd.DataFrame:
    """Each car's deviation from the typical schedule is interpolated between its own reads:
    if a car is 3 min late at SLR-1 and 5 min late at SLR-3, it was ~4 min late at SLR-2."""
    dev = M - offsets
    dev = dev.interpolate(axis=1, limit_area="inside")          # between two reads
    dev = dev.ffill(axis=1).bfill(axis=1)                       # before the first / after the last read
    return dev + offsets


def validate(M: pd.DataFrame, offsets: pd.Series, frac: float = 0.02, seed: int = 7) -> pd.DataFrame:
    """Hide a random share of real reads, re-estimate them, return (station, absolute error in minutes)."""
    rng = np.random.default_rng(seed)
    known = M.notna().to_numpy()
    hide = known & (rng.random(M.shape) < frac)
    M_test = M.mask(hide)
    est = fill_missing(M_test, offsets)
    _, col = np.where(hide)
    return pd.DataFrame({"mes_station": M.columns.to_numpy()[col],
                         "error": np.abs(est.to_numpy()[hide] - M.to_numpy()[hide])})


def build_passages(stations: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    p = load("mes_vehicle_passages.csv.gz")
    v = load("vehicles.csv")
    route = list(stations[~stations.mes_station.isin(BOOTHS)].sort_values("sequence").mes_station)
    M = minutes_matrix(p, v, route)
    offsets = M.median()
    errors = validate(M, offsets)
    filled = fill_missing(M, offsets)

    long = filled.stack().rename("min").reset_index()
    long["inferred"] = M.stack(future_stack=True).reindex(pd.MultiIndex.from_frame(long[["vin", "mes_station"]])).isna().to_numpy()
    # Uncertainty of an inferred passage = 95th-percentile validation error at that station.
    # It is large right after buffers (P-INS, T1-01) where cars wait for an unpredictable time.
    p95 = errors.groupby("mes_station").error.quantile(0.95)
    long["uncertainty_min"] = np.where(long.inferred, long.mes_station.map(p95), 0.0)
    long = long.merge(v[["vin", "body_start_at"]], on="vin")
    long["passed_at"] = (long.body_start_at + pd.to_timedelta(long["min"], unit="m")).dt.round("s")
    reads = p.set_index(["vin", "mes_station"]).passed_at
    real = ~long.inferred
    long.loc[real, "passed_at"] = reads.reindex(pd.MultiIndex.from_frame(long.loc[real, ["vin", "mes_station"]])).to_numpy()

    # Booth and oven: each car goes through exactly one pair (TC-n -> OV-n). If one of the two was read, the
    # other is the same n; if neither was read, the booth is unknown and no booth passage is created.
    b = p[p.mes_station.isin(BOOTHS)].copy()
    b["n"] = b.mes_station.str[-1]
    have = b.pivot(index="vin", columns="mes_station", values="passed_at")
    booth_rows = []
    pr_time = long[long.mes_station == "P-PR"].set_index("vin").passed_at
    off_tc = (have.get("TC-1").fillna(have.get("TC-2")) - pr_time.reindex(have.index)).median()
    off_ov = (have.get("OV-1").fillna(have.get("OV-2")) - have.get("TC-1").fillna(have.get("TC-2"))).median()
    for vin in v.vin:
        if vin in have.index:
            row = have.loc[vin]
            n = next(s[-1] for s in BOOTHS if pd.notna(row.get(s)))
            tc, ov = row.get(f"TC-{n}"), row.get(f"OV-{n}")
            if pd.isna(tc):
                tc, tc_inf = ov - off_ov, True
            else:
                tc_inf = False
            if pd.isna(ov):
                ov, ov_inf = tc + off_ov, True
            else:
                ov_inf = False
            booth_rows += [(vin, f"TC-{n}", tc, tc_inf), (vin, f"OV-{n}", ov, ov_inf)]
    booth = pd.DataFrame(booth_rows, columns=["vin", "mes_station", "passed_at", "inferred"])
    booth["passed_at"] = booth.passed_at.dt.round("s")
    booth["uncertainty_min"] = np.where(booth.inferred, float(p95.median()), 0.0)
    out = pd.concat([long[["vin", "mes_station", "passed_at", "inferred", "uncertainty_min"]], booth],
                    ignore_index=True)
    out["booth_unknown"] = False
    unknown = sorted(set(v.vin) - set(have.index))
    out = out.merge(stations[["mes_station", "fl"]], on="mes_station")
    return out.sort_values(["vin", "passed_at"]).reset_index(drop=True), errors, unknown, off_tc


def equipment_at_stations(assets: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Equipment that touches the car, per MES station, with its validity window."""
    a = assets.copy()
    moved = a.description.fillna("").str.extract(r"Relocated .* in ([A-Z][a-z]{2})-(\d{4})")
    a["valid_from"] = pd.to_datetime("1 " + moved[0] + " " + moved[1], errors="coerce")
    st_fl = dict(zip(stations.fl, stations.mes_station))
    rows = []
    robots = a[a.asset_type.isin(["Robot", "SealerRobot", "PaintRobot"])]
    for r in robots.itertuples():
        mes = st_fl.get(r.parent_fl)
        if mes:
            rows.append((mes, r.functional_location, r.asset_type, r.valid_from))
            for c in a[(a.parent_fl == r.functional_location) & (a.asset_type == "Dispenser")].itertuples():
                rows.append((mes, c.functional_location, c.asset_type, r.valid_from))
    return pd.DataFrame(rows, columns=["mes_station", "fl", "asset_type", "valid_from"])


def build_processed_by(passages: pd.DataFrame, eq: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    pe = passages.merge(eq, on="mes_station", suffixes=("_station", ""))
    pe = pe[pe.valid_from.isna() | (pe.passed_at >= pe.valid_from)]          # robot moved: only after the move
    conf = np.where(~pe.inferred, 0.95, np.where(pe.uncertainty_min <= TAKT_MIN, 0.85, 0.60))
    pe = pe.assign(start=pe.passed_at, end=pe.passed_at + pd.Timedelta(minutes=TAKT_MIN), method="mes_station",
                   confidence=conf)
    station_based = pe[["vin", "fl", "asset_type", "start", "end", "inferred", "method", "confidence"]]

    # Nutrunners: the torque result names the tool channel, so this link is observed, not inferred.
    tq = load("torque_results.csv.gz")
    nr = assets[assets.asset_type == "Nutrunner"].functional_location
    nr_by_no = {fl.split("-")[-1]: fl for fl in nr}
    t = tq[tq.tool_id.str.startswith("TC")].copy()
    t["fl"] = t.tool_id.str.replace("TC", "NR").map(nr_by_no)
    tool_based = (t.groupby(["vin", "fl"]).timestamp.agg(["min", "max"]).reset_index()
                  .rename(columns={"min": "start", "max": "end"})
                  .assign(asset_type="Nutrunner", inferred=False, method="torque_result", confidence=0.99))
    return pd.concat([station_based, tool_based], ignore_index=True)


def build_tools(assets: pd.DataFrame) -> pd.DataFrame:
    tq = load("torque_results.csv.gz")
    nr = {fl.split("-")[-1]: fl for fl in assets[assets.asset_type == "Nutrunner"].functional_location}
    tools = pd.DataFrame({"tool_id": sorted(tq.tool_id.unique())})
    tools["kind"] = np.where(tools.tool_id.str.startswith("TC"), "controller_channel", "hand_wrench")
    tools["equipment_fl"] = tools.tool_id.str.replace("TC", "NR").map(nr)
    tools["controller_fl"] = tools.equipment_fl + "-TC"
    return tools


def build_part_lots() -> pd.DataFrame:
    g = load("part_lot_genealogy.csv.gz")
    b = load("press_panel_batches.csv").rename(columns={"batch_id": "lot_id"})
    g["part_uid"] = g.vin + "|" + g.part_no
    return g.merge(b[["lot_id", "press_line", "die_id", "produced_from", "produced_to"]], on="lot_id", how="left")


def trace_vin(vin: str, passages, processed, part_lots, ts_path) -> list[str]:
    """Human-readable end-to-end trace of one VIN (used in the report and the demo)."""
    d = load("quality_defects.csv")
    tq = load("torque_results.csv.gz")
    out = [f"### End-to-end trace of `{vin}`", "", "| Time | MES station | Functional location | Inferred |",
           "|---|---|---|---|"]
    for r in passages[passages.vin == vin].itertuples():
        out.append(f"| {r.passed_at:%d %b %H:%M:%S} | {r.mes_station} | `{r.fl}` | {'**yes**' if r.inferred else ''} |")
    pb = processed[(processed.vin == vin)]
    out += ["", "Equipment that processed it:", ""]
    for kind, g in pb.groupby("asset_type"):
        out.append(f"- {kind}: " + ", ".join(f"`{f.split('-', 1)[1]}`" for f in g.fl))
    sealer = pb[pb.fl.str.endswith("SR03")]
    if len(sealer):
        s = sealer.iloc[0]
        ts = pd.read_parquet(ts_path, filters=[("tag_name", "=", "DDN1_PNT_SL_SR03_NOZTEMP.PV")])
        w = ts[(ts.timestamp >= s.start.floor("min")) & (ts.timestamp <= s.end.ceil("min"))]
        out.append(f"- Sealer SR03 nozzle temperature while it sealed this car: {w.value.min():.1f}-{w.value.max():.1f} "
                   "C (set 45, alarm < 38)" if len(w) else "- Sealer SR03 nozzle temperature: no value in window")
    lots = part_lots[part_lots.vin == vin]
    out += ["", "Parts and lots: " + ", ".join(f"{r.part_no} `{r.lot_id}`" for r in lots.itertuples())]
    nok = tq[(tq.vin == vin) & (tq.status == "NOK")]
    out += [f"Torque: {len(tq[tq.vin == vin])} results, {len(nok)} NOK"]
    for r in d[d.vin == vin].itertuples():
        out.append(f"Defect: **{r.defect_desc}** ({r.defect_code}) at {r.inspection_point}, {r.location}, "
                   f"{r.detected_at:%d %b %H:%M}")
    return out + [""]


def main() -> None:
    assets = pd.read_parquet(STAGING / "assets.parquet")
    stations = pd.read_parquet(STAGING / "stations.parquet")
    passages, errors, unknown, _ = build_passages(stations)
    eq = equipment_at_stations(assets, stations)
    processed = build_processed_by(passages, eq, assets)
    tools = build_tools(assets)
    part_lots = build_part_lots()
    for name, df in [("passages_full", passages), ("processed_by", processed), ("tools", tools),
                     ("part_lots", part_lots)]:
        df.to_parquet(STAGING / f"{name}.parquet", index=False)

    raw = load("mes_vehicle_passages.csv.gz")
    inf = passages[passages.inferred]
    by_station = inf.mes_station.value_counts()
    d = load("quality_defects.csv")
    # demo VIN: a roof-ditch leak whose SLR-2 passage had to be inferred (reader offline)
    cand = inf[inf.mes_station == "SLR-2"].vin
    demo = d[(d.defect_code == "WL-101") & d.vin.isin(cand)].vin.iloc[0]
    e = errors.error
    out = ["# Part C6 – VIN traceability", "", "Generated by `python -m ddn.trace`.", "",
           "## Passages", "",
           f"- RFID reads in the data: {len(raw):,}; passages after filling: {len(passages):,}",
           f"- **Inferred passages: {len(inf):,}** ({len(inf) / len(passages):.1%}), flagged `inferred=True`",
           f"- Most inferred at: " + ", ".join(f"{k} {v}" for k, v in by_station.head(5).items()),
           f"- Booth/oven unknown (neither TC nor OV read): {len(unknown)} VINs – no booth passage created: "
           + ", ".join(f"`{x}`" for x in unknown),
           "", "### Validation of the inference", "",
           f"Hid {len(errors):,} real reads at random (2 %), re-estimated them, compared with the true time:", "",
           f"| Mean abs. error | Median | 95th percentile | Max | Within 1 takt ({TAKT_MIN} min) |",
           "|---:|---:|---:|---:|---:|",
           f"| {e.mean():.2f} min | {e.median():.2f} min | {e.quantile(.95):.2f} min | "
           f"{e.max():.2f} min | {(e <= TAKT_MIN).mean():.1%} |", "",
           "Errors are not uniform: they are large right after **buffers**, where painted bodies wait for an "
           "unpredictable time before trim. Each inferred passage therefore stores `uncertainty_min` = the "
           "95th-percentile error at its station, and its processedBy edges get confidence 0.85 "
           f"(uncertainty <= 1 takt) or 0.60 (larger).", "",
           "| Station | Hidden reads | Median error | 95th pct error |", "|---|---:|---:|---:|"]
    worst = errors.groupby("mes_station").error.agg(["size", "median", lambda x: x.quantile(.95)])
    worst.columns = ["n", "median", "p95"]
    out += [f"| {k} | {int(r.n)} | {r['median']:.2f} min | {r.p95:.2f} min |"
            for k, r in worst.sort_values("p95", ascending=False).head(6).iterrows()]
    out += ["",
           "An inferred passage is therefore good enough to say *which car* was at a station during a "
           "multi-minute anomaly window, which is what the root-cause queries need - except right after a "
           "buffer, where it is flagged with low confidence. Queries can always exclude `inferred=True`.", "",
           "## processedBy (VIN -> equipment)", "",
           "| Equipment type | Edges | Source |", "|---|---:|---|"]
    for (t, m), n in processed.groupby(["asset_type", "method"]).size().items():
        out.append(f"| {t} | {n:,} | {m} |")
    out += ["", f"Total processedBy edges: {len(processed):,}. Tools: {len(tools)} "
            f"({(tools.kind == 'hand_wrench').sum()} hand wrench). Part fitments: {len(part_lots):,}; "
            f"press-batch lots linked to press line and die: {part_lots.die_id.notna().sum():,}.", ""]
    out += trace_vin(demo, passages, processed, part_lots, STAGING / "timeseries")
    path = REPORTS / "10_vin_traceability.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"passages {len(passages):,} ({len(inf):,} inferred), validation MAE {errors.error.mean():.2f} min, "
          f"processedBy {len(processed):,}, demo {demo} -> {path}")


if __name__ == "__main__":
    main()
