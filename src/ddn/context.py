"""Part C (structure): MES stations, process flow (`feeds`) and alarm sources.

1. MES station code -> functional location (the Station node then carries both identities).
2. `feeds` edges, upstream -> downstream:
     - vehicle route: consecutive MES stations in the order cars actually pass them
     - air handling units -> the booth they condition (AHU-TC1 -> booth A, ...)
     - press lines -> the body station where their panels are fitted (from part genealogy)
3. Alarm source path -> asset: normalise separators (. _ /), S4 -> ST04, prefix DDN1,
   then walk up the path until an existing functional location is found.
   Duplicates (same time, source, code) are flagged, not deleted, and every alarm
   code is explained with the manual's message and causes.

Run:  python -m ddn.context     (writes data/staging/stations.parquet, feeds.parquet, alarms.parquet,
                                  reports/09_stations_alarms.md)
"""
from __future__ import annotations

import re

import pandas as pd

from .config import REPORTS, STAGING
from .load import load


def mes_to_fl(code: str) -> str | None:
    """Rule set from the plant overview's vehicle route and the asset master."""
    rules = [
        (r"^B([123])-(\d{2})$", r"DDN1-BIW-L\1-ST\2"),
        (r"^BIQ-(\d)$", r"DDN1-BIW-QI-ST0\1"),
        (r"^SLR-(\d)$", r"DDN1-PNT-SL-ST0\1"),
        (r"^P-INS$", "DDN1-PNT-INSP-ST01"),
        (r"^P-(PT|ED|EDO|PR)$", r"DDN1-PNT-\1"),
        (r"^TC-(\d)$", r"DDN1-PNT-TC\1"),
        (r"^OV-(\d)$", r"DDN1-PNT-OV\1"),
        (r"^T([12])-(\d{2})$", r"DDN1-ASM-TR\1-ST\2"),
        (r"^C1-(\d{2})$", r"DDN1-ASM-CH1-ST\1"),
        (r"^F1-(\d{2})$", r"DDN1-ASM-FN1-ST\1"),
        (r"^EOL-(ALN|RT|WT|AUD)$", r"DDN1-ASM-EOL-\1"),
    ]
    for pat, rep in rules:
        if re.match(pat, code):
            return re.sub(pat, rep, code)
    return None


def build_stations(assets: pd.DataFrame) -> pd.DataFrame:
    st = load("mes_station_master.csv")
    p = load("mes_vehicle_passages.csv.gz").merge(load("vehicles.csv")[["vin", "body_start_at"]], on="vin")
    order = ((p.passed_at - p.body_start_at).dt.total_seconds() / 60).groupby(p.mes_station).median()
    fls = set(assets.functional_location)
    st["fl"] = st.mes_station.map(mes_to_fl)
    st["fl_exists"] = st.fl.isin(fls)
    st["minutes_from_body_start"] = st.mes_station.map(order).round(1)
    st["sequence"] = st.minutes_from_body_start.rank(method="dense").astype(int)
    st["area_fixed"] = st.area.where(~st.mes_station.str.startswith("OV-"), "PAINT")   # data has ASSY: wrong
    return st.sort_values("sequence")


def build_feeds(stations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # 1. vehicle route. Booths/ovens run in parallel: TC-1/TC-2 both follow P-PR, OV-n follows TC-n.
    seq = stations[~stations.mes_station.isin(["TC-1", "TC-2", "OV-1", "OV-2"])].sort_values("sequence")
    fl = dict(zip(stations.mes_station, stations.fl))
    route = list(seq.mes_station)
    for a, b in zip(route, route[1:]):
        if (a, b) == ("P-PR", "P-INS"):
            continue                                            # replaced by the two parallel paths below
        rows.append((fl[a], fl[b], "process_flow", f"MES route {a} -> {b}"))
    for n in ("1", "2"):
        rows += [(fl["P-PR"], fl[f"TC-{n}"], "process_flow", f"MES route P-PR -> TC-{n}"),
                 (fl[f"TC-{n}"], fl[f"OV-{n}"], "process_flow", f"booth {n} is paired with oven {n}"),
                 (fl[f"OV-{n}"], fl["P-INS"], "process_flow", f"MES route OV-{n} -> P-INS")]
    # 2. air handling units condition the booths (plant overview + DWG-PNT-AHU-301)
    rows += [("DDN1-PNT-AHU-AHUTC1", fl["TC-1"], "conditions", "AHU-01 -> topcoat booth A"),
             ("DDN1-PNT-AHU-AHUTC2", fl["TC-2"], "conditions", "AHU-02 -> topcoat booth B"),
             ("DDN1-PNT-AHU-AHUPR", fl["P-PR"], "conditions", "AHU-03 -> primer booth")]
    # 3. press lines supply panels to the body station where the part is fitted (part genealogy)
    g = load("part_lot_genealogy.csv.gz")
    batches = load("press_panel_batches.csv")
    for part, line in batches.groupby("part_no").press_line.first().items():
        st = g.loc[g.part_no == part, "fitted_mes_station"].mode()[0]
        rows.append((f"DDN1-PRS-{line}", fl[st], "supplies", f"{part} panels from {line} fitted at {st}"))
    return pd.DataFrame(rows, columns=["from_fl", "to_fl", "relation", "evidence"])


def normalise_source(src: str) -> str:
    """'BIW/L2/S4/RB07', 'BIW.L2.ST04.RB07', 'BIW_L2_ST04_RB07' -> 'DDN1-BIW-L2-ST04-RB07'."""
    parts = re.split(r"[._/]", src.strip().upper())
    parts = [f"ST{int(p[1:]):02d}" if re.fullmatch(r"S\d{1,2}", p) else p for p in parts]
    return "DDN1-" + "-".join(parts)


def link_alarms(assets: pd.DataFrame, stations: pd.DataFrame, codes: pd.DataFrame) -> pd.DataFrame:
    al = load("alarms_andon_events.csv")
    fls = set(assets.functional_location)
    mes = dict(zip(stations.mes_station, stations.fl))
    out = []
    for r in al.itertuples():
        if r.source in mes:                                   # andon calls come from MES stations
            out.append((r.event_id, mes[r.source], "mes_station", 0.97))
            continue
        cand = normalise_source(r.source)
        parts = cand.split("-")
        fl, method, conf = None, "none", 0.0
        for i in range(len(parts), 2, -1):                    # walk up until an existing FL is found
            c = "-".join(parts[:i])
            if c in fls:
                fl = c
                method, conf = ("path_exact", 0.97) if i == len(parts) else ("path_parent", 0.85)
                break
        out.append((r.event_id, fl, method, conf))
    links = pd.DataFrame(out, columns=["event_id", "functional_location", "method", "confidence"])
    al = al.merge(links, on="event_id")
    al["source_norm"] = al.source.map(lambda s: s if s in mes else normalise_source(s))
    al["is_duplicate"] = al.duplicated(["event_time", "source_norm", "code"], keep="first")
    meaning = codes.drop_duplicates("code").set_index("code").text
    al["manual_meaning"] = al.code.map(meaning)
    return al


def main() -> None:
    assets = pd.read_parquet(STAGING / "assets.parquet")
    stations = build_stations(assets)
    feeds = build_feeds(stations)
    codes = pd.read_parquet(STAGING / "doc_alarm_codes.parquet")
    alarms = link_alarms(assets, stations, codes)
    stations.to_parquet(STAGING / "stations.parquet", index=False)
    feeds.to_parquet(STAGING / "feeds.parquet", index=False)
    alarms.to_parquet(STAGING / "alarms.parquet", index=False)

    unres = alarms[alarms.functional_location.isna()]
    out = ["# Part C – MES stations, process flow and alarm sources", "",
           "Generated by `python -m ddn.context`.", "",
           "## MES station -> functional location", "",
           f"{stations.fl_exists.sum()} of {len(stations)} MES stations map to an existing functional location. "
           "OV-1/OV-2 are labelled area ASSY in the MES master; they are paint ovens (corrected).", "",
           "| Seq | MES | Description | Functional location | Exists | Minutes after body start |",
           "|---:|---|---|---|---|---:|"]
    out += [f"| {r.sequence} | `{r.mes_station}` | {r.description} | `{r.fl}` | {'yes' if r.fl_exists else '**no**'} | "
            f"{r.minutes_from_body_start} |" for r in stations.itertuples()]
    out += ["", f"## `feeds` edges ({len(feeds)})", "", "| From | To | Relation | Evidence |", "|---|---|---|---|"]
    out += [f"| `{r.from_fl}` | `{r.to_fl}` | {r.relation} | {r.evidence} |" for r in feeds.itertuples()]
    by = alarms.groupby("method").size()
    out += ["", "## Alarm and andon sources", "",
            f"- {len(alarms):,} events; {alarms.functional_location.notna().mean():.1%} linked to an asset "
            f"({', '.join(f'{k} {v:,}' for k, v in by.items())})",
            f"- Duplicates flagged: {alarms.is_duplicate.sum():,} (same time, normalised source, code)",
            f"- Alarm codes explained by a manual: {alarms.manual_meaning.notna().mean():.1%} of events", ""]
    if len(unres):
        out += ["Unresolved sources:", ""] + [f"- `{s}` ({n})" for s, n in unres.source.value_counts().items()]
    ex = alarms[alarms.source.str.contains("/")].drop_duplicates("source").head(8)
    out += ["", "| Raw source | Normalised | Asset | Method |", "|---|---|---|---|"]
    out += [f"| `{r.source}` | `{r.source_norm}` | `{r.functional_location}` | {r.method} |" for r in ex.itertuples()]
    path = REPORTS / "09_stations_alarms.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"stations {stations.fl_exists.sum()}/{len(stations)} mapped; feeds {len(feeds)}; alarms linked "
          f"{alarms.functional_location.notna().mean():.1%}, duplicates {alarms.is_duplicate.sum()} -> {path}")


if __name__ == "__main__":
    main()
