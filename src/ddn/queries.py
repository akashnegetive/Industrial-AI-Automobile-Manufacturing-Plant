"""Part D - the seven required graph queries (Cypher), run against Neo4j.

Each query is plain Cypher with parameters, tagged with the ontology *view* it belongs
to (Maintenance / Quality / Traceability - the Cognite "views" over one storage model).
Time-series values are not in the graph: queries return a TimeSeries node's `store_uri`
and `values()` reads the window from Parquet. That is the "graph holds pointers" design.

Run (graph loaded):  python -m ddn.queries     (writes reports/12_graph_queries.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .config import REPORTS, ROOT, STAGING
from .graph import driver
from .review import build_queue

# Valid partOf edges only: the relocated robot's old partOf has valid_to set.
CURRENT = "all(x IN rels WHERE x.valid_to IS NULL)"

Q = {}

Q["D1"] = dict(view="Maintenance", title="All temperature sensors in Topcoat Oven 2, with latest value and open work orders",
               cypher=f"""
MATCH path = (a:Asset)-[:partOf*0..3]->(:Asset {{fl: $oven}})
WITH a, relationships(path) AS rels WHERE {CURRENT}
MATCH (a)-[:hasTimeSeries]->(t:TimeSeries {{isa51_code: 'TT'}})
OPTIONAL MATCH (a)-[:hasWorkOrder]->(w:WorkOrder)
WITH a, t, collect(w) AS wos
RETURN a.fl AS equipment, t.tag AS sensor, t.unit AS unit_in_source, t.unit_canonical AS unit,
       round(t.latest_value, 1) AS latest_value, t.latest_at AS latest_at,
       [w IN wos WHERE w.closed_at IS NULL OR w.closed_at > $as_of | w.wo_number] AS open_work_orders,
       size(wos) AS work_orders_12m
ORDER BY equipment, sensor""", params={"oven": "DDN1-PNT-OV2", "as_of": datetime(2026, 9, 15)})

Q["D2"] = dict(view="Quality", title="A VIN with a water-leak defect: which sealer robot and nozzle processed it, "
               "and what were sealer temperature and flow at that time",
               cypher="""
MATCH (v:Vehicle {vin: $vin})-[:hasDefect]->(d:Defect) WHERE d.defect_family = 'water leak'
MATCH (v)-[p:processedBy]->(e:Asset) WHERE e.asset_type IN ['SealerRobot', 'Dispenser']
OPTIONAL MATCH (e)-[:hasTimeSeries]->(t:TimeSeries) WHERE t.store_uri IS NOT NULL
RETURN v.vin AS vin, d.defect_code + ' ' + d.location AS defect, e.fl AS equipment, e.asset_type AS type,
       p.start AS start, p.end AS end, p.inferred AS passage_inferred, p.confidence AS edge_confidence,
       t.tag AS signal, t.store_uri AS store_uri
ORDER BY equipment, signal""", params={"vin": "MDDA5XK0XD004375"})

Q["D3"] = dict(view="Traceability", title="All VINs with out-of-spec wheel-nut torque in the last week, the nutrunner used, "
               "and its last calibration work order",
               cypher="""
MATCH (v:Vehicle)-[:hasTorqueResult]->(r:TorqueResult)-[:tightenedBy]->(tool:Tool)
WHERE r.joint_id STARTS WITH 'WHEEL' AND r.status = 'NOK' AND r.attempt = 1
  AND r.timestamp >= $from AND r.timestamp < $to
MATCH (tool)-[:partOf]->(ctrl:Component)-[:partOf]->(nr:Asset)
OPTIONAL MATCH (x:Asset)-[:hasWorkOrder]->(w:WorkOrder {wo_type: 'CAL'})
  WHERE x IN [nr, ctrl] AND w.created_at <= r.timestamp
WITH v, r, tool, nr, w ORDER BY w.created_at DESC
WITH v, r, tool, nr, collect(w)[0] AS last_cal
OPTIONAL MATCH (v)-[:hasTorqueResult]->(re:TorqueResult {joint_id: r.joint_id, attempt: 2})
RETURN v.vin AS vin, r.joint_id AS joint, r.torque_nm AS torque_nm, r.timestamp AS at, tool.tool_id AS tool,
       nr.fl AS nutrunner, last_cal.wo_number AS last_calibration_wo, last_cal.created_at AS calibrated_at,
       last_cal.short_text AS calibration_text, re IS NOT NULL AS re_hit
ORDER BY at""", params={"from": datetime(2026, 8, 29), "to": datetime(2026, 9, 5)})

Q["D3b"] = dict(view="Maintenance", title="Calibration coverage: last linked calibration work order per nutrunner",
                cypher="""
MATCH (n:Equipment {asset_type: 'Nutrunner'})
OPTIONAL MATCH (x:Asset)-[:hasWorkOrder]->(w:WorkOrder {wo_type: 'CAL'}) WHERE x = n OR (x)-[:partOf]->(n)
WITH n, count(w) AS calibrations_12m, max(w.created_at) AS last_calibration
RETURN n.fl AS nutrunner, calibrations_12m, last_calibration
ORDER BY calibrations_12m, last_calibration""", params={})

Q["D4"] = dict(view="Quality", title="Spike in paint craters at topcoat inspection: upstream equipment via feeds, "
               "ranked by alarms and humidity excursions in the prior 2 hours",
               cypher="""
MATCH (insp:Asset {fl: $inspection})<-[:feeds*1..3]-(u:Asset)
OPTIONAL MATCH (e:Asset)-[:partOf*0..2]->(u)
WITH DISTINCT u, e
OPTIONAL MATCH (al:Alarm)-[:raisedBy]->(e)
  WHERE al.event_time >= $from AND al.event_time <= $to AND NOT al.is_duplicate
OPTIONAL MATCH (e)-[:hasTimeSeries]->(t:TimeSeries) WHERE t.signal = 'RH' AND t.store_uri IS NOT NULL
RETURN u.fl AS upstream, count(DISTINCT al) AS alarms, collect(DISTINCT al.code) AS alarm_codes,
       collect(DISTINCT t.store_uri) AS humidity_series
ORDER BY alarms DESC""", params={"inspection": "DDN1-PNT-INSP-ST01"})

Q["D5"] = dict(view="Traceability", title="All VINs that received parts from a suspect supplier lot (recall scope)",
               cypher="""
MATCH (l:SupplierLot {lot_id: $lot})<-[:fromLot]-(:Part)<-[c:containsPart]-(v:Vehicle)
OPTIONAL MATCH (v)-[:hasDefect]->(d:Defect) WHERE d.defect_code = 'WL-104'
WITH l, v, c, count(d) > 0 AS leaked
RETURN l.lot_id AS lot, l.supplier AS supplier, date(c.fitted_at) AS fitted_on, count(v) AS vehicles,
       sum(CASE WHEN leaked THEN 1 ELSE 0 END) AS with_door_leak
ORDER BY fitted_on""", params={"lot": "WS-260904-B"})

Q["D6"] = dict(view="Maintenance", title="Tags and work orders still not linked to any asset, and edges below 0.8 confidence "
               "by method",
               cypher="""
CALL () { MATCH (t:TimeSeries) WHERE NOT ()-[:hasTimeSeries]->(t) RETURN 'tag' AS kind, count(t) AS unlinked,
          collect(t.tag)[..5] AS examples }
RETURN kind, unlinked, examples
UNION ALL
CALL () { MATCH (w:WorkOrder) WHERE NOT ()-[:hasWorkOrder]->(w) RETURN 'work order' AS kind, count(w) AS unlinked,
          collect(w.wo_number + ' ' + w.short_text)[..5] AS examples }
RETURN kind, unlinked, examples""", params={})

Q["D6b"] = dict(view="Maintenance", title="Edges below 0.8 confidence, by type and method", cypher="""
MATCH ()-[r]->() WHERE r.confidence < 0.8
RETURN type(r) AS relationship, r.method AS method, count(*) AS edges, round(min(r.confidence), 2) AS min_conf,
       round(max(r.confidence), 2) AS max_conf
ORDER BY edges DESC""", params={})

Q["D7"] = dict(view="Quality", title="Plant head: how many cars built in these two weeks carry a known risk, "
               "and how many of them did inspection catch?",
               cypher="""
CALL () {
  MATCH (v:Vehicle)-[:hasTorqueResult]->(r:TorqueResult {status: 'NOK', attempt: 1})
  WHERE r.joint_id STARTS WITH 'WHEEL'
    AND NOT EXISTS { (v)-[:hasTorqueResult]->(:TorqueResult {joint_id: r.joint_id, attempt: 2}) }
  RETURN DISTINCT v, 'wheel nut NOK, never re-hit' AS risk, ['AU-077'] AS catches
  UNION
  MATCH (v:Vehicle)-[c:containsPart]->(:Part)-[:fromLot]->(:SupplierLot {lot_id: $lot})
  WHERE c.fitted_at >= $lot_from
  RETURN DISTINCT v, 'door seal from suspect lot' AS risk, ['WL-104'] AS catches
  UNION
  MATCH (v:Vehicle)-[p:processedBy]->(:Asset {fl: $sealer}) WHERE p.start >= $seal_from AND p.start <= $seal_to
  RETURN DISTINCT v, 'sealed while SR03 nozzle was cold' AS risk, ['WL-101'] AS catches
  UNION
  MATCH (v:Vehicle)-[p:processedBy]->(:Asset {fl: $robot}) WHERE p.start >= $weld_from AND p.start <= $weld_to
  RETURN DISTINCT v, 'welded while R07 current was low' AS risk, ['BW-017'] AS catches
}
OPTIONAL MATCH (v)-[:hasDefect]->(d:Defect) WHERE d.defect_code IN catches
WITH risk, v, count(d) > 0 AS caught
RETURN risk, count(v) AS vehicles_at_risk, sum(CASE WHEN caught THEN 1 ELSE 0 END) AS caught_by_inspection,
       sum(CASE WHEN caught THEN 0 ELSE 1 END) AS not_caught
ORDER BY vehicles_at_risk DESC""", params={})


# ----------------------------------------------------------------- helpers
def _native(v):
    """Neo4j temporal types -> Python datetime/date (they expose .to_native())."""
    return v.to_native() if hasattr(v, "to_native") else v


def run(session, key: str, **override) -> pd.DataFrame:
    q = Q[key]
    rows = session.run(q["cypher"], **{**q["params"], **override})
    return pd.DataFrame([{k: _native(v) for k, v in r.items()} for r in rows])


def values(store_uri: str, start, end) -> pd.Series:
    """Read a time-series window from the Parquet store a TimeSeries node points to."""
    tag = store_uri.split("tag_name=", 1)[1]
    ts = pd.read_parquet(STAGING / "timeseries", filters=[("tag_name", "=", tag)])
    return ts[(ts.timestamp >= pd.Timestamp(start).floor("min")) & (ts.timestamp <= pd.Timestamp(end).ceil("min"))
              ].set_index("timestamp").value


def problem_windows() -> dict:
    """Out-of-spec windows found in Part B (re-computed from the time series, not typed in)."""
    from . import problems as P
    P.DATA = P._Data()
    w = {}
    s, e, _ = P.window_of("DDN1_BIW_L2_R07_WELDCUR.PV", lambda x: (x > 3) & (x < 9.5))
    w["weld"] = (s.to_pydatetime(), e.to_pydatetime())
    s, e, _ = P.window_of("DDN1_PNT_SL_SR03_NOZTEMP.PV", lambda x: (x > 28) & (x < 42))
    w["seal"] = ((s - pd.Timedelta("5min")).to_pydatetime(), (e + pd.Timedelta("5min")).to_pydatetime())
    return w


def table(df: pd.DataFrame, n: int = 15) -> list[str]:
    if df.empty:
        return ["*(no rows)*"]
    d = df.head(n).copy()
    def fmt(x):
        if not isinstance(x, list) and pd.isna(x):
            return ""
        if isinstance(x, datetime):
            return x.strftime("%Y-%m-%d %H:%M")
        if hasattr(x, "isoformat") and not isinstance(x, str):          # datetime.date
            return x.isoformat()
        return ", ".join(map(str, x)) if isinstance(x, list) else x
    for c in d.columns:
        d[c] = d[c].map(fmt)
    out = ["| " + " | ".join(d.columns) + " |", "|" + "---|" * len(d.columns)]
    out += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    if len(df) > n:
        out.append(f"\n*… {len(df) - n} more rows*")
    return out


def section(key: str, df: pd.DataFrame, notes: list[str], params: dict | None = None) -> list[str]:
    q = Q[key]
    p = {**q["params"], **(params or {})}
    shown = ", ".join(f"`{k}` = {v}" for k, v in p.items()) or "none"
    return [f"## {key}. {q['title']}", "", f"*View: {q['view']}. Parameters: {shown}.*", "",
            "```cypher" + q["cypher"].rstrip(), "```", "", *table(df), "", *notes, ""]


def main() -> None:
    out = ["# Part D – Graph queries", "",
           "Generated by `python -m ddn.queries` against the Neo4j graph loaded by `python -m ddn.graph`. "
           "Every query is shown with its Cypher and its real output.", ""]
    with driver() as drv, drv.session() as s:
        d1 = run(s, "D1")
        out += section("D1", d1, [f"- {len(d1)} temperature sensors (deg F in WinCC, stored as deg C). "
                                  f"Open work orders: {sum(len(x) for x in d1.open_work_orders)} – every work order "
                                  "in the export is closed, so the list is empty by data, not by mistake."])

        d2 = run(s, "D2")
        notes = []
        for r in d2.dropna(subset=["store_uri"]).itertuples():
            vals = values(r.store_uri, r.start, r.end)
            notes.append(f"- `{r.signal}` while `{r.equipment.split('-', 3)[-1]}` worked on the car "
                         f"({r.start:%H:%M}–{r.end:%H:%M}): "
                         + (f"{vals.min():.1f}–{vals.max():.1f}" if len(vals) else "no value"))
        out += section("D2", d2.drop(columns=["store_uri"]), notes + [
            "- The SLR-2 passage is `inferred` (reader RD-SLR-2 was offline), so its edges carry confidence 0.85. "
            "Values come from Parquet through `store_uri`; the graph only stores the pointer."])

        d3 = run(s, "D3")
        late = run(s, "D3", **{"from": datetime(2026, 9, 8), "to": datetime(2026, 9, 15)})
        out += section("D3", d3, [
            f"- {d3.vin.nunique()} VINs, {len(d3)} NOK first rundowns, all on `{', '.join(sorted(d3.tool.unique()))}`; "
            f"{(~d3.re_hit).sum()} were never re-hit.",
            f"- Run for the final week instead (8–15 Sep): {len(late)} rows – the problem was fixed on 4 Sep.",
            "- *Last calibration WO* is empty: NR14 has **no linked calibration work order in the 12 months** "
            "before the incident (manual MAN-TQX-DC500: calibrate every 12 months). See D3b.",
            "- The repair WO 4102964 ('NR14 transducer calibration – found offset', 4 Sep) is not in the graph yet: "
            "the matcher gave it 0.66, which is in the review band. An engineer approving it in the review app "
            "adds it on the next run – the review loop working as designed."])
        d3b = run(s, "D3b")
        out += section("D3b", d3b, [
            f"- {(d3b.calibrations_12m == 0).sum()} of {len(d3b)} nutrunners have no linked calibration in 12 months: "
            f"{', '.join(d3b[d3b.calibrations_12m == 0].nutrunner)}. NR14 is the one that drifted on 3 Sep.",
            "- The controllers' `T-40 Calibration due` alarm is no help: it fires 13–25 times in two weeks on "
            "*every* nutrunner, so it is noise operators learn to ignore.",
            "- Caveat: an unlinked calibration WO (review band / backlog) would not be counted."])

        crater = pd.DataFrame([dict(r) for r in s.run(
            "MATCH (d:Defect {defect_family: 'paint'})-[:detectedAt]->(:Asset {fl: 'DDN1-PNT-INSP-ST01'}) "
            "WHERE d.defect_code = 'PD-020' RETURN d.detected_at AS t")]).map(_native)
        spike = pd.to_datetime(crater.t).dt.floor("h").value_counts().idxmax()
        to, frm = spike.to_pydatetime() + timedelta(hours=1), spike.to_pydatetime() - timedelta(hours=2)
        d4 = run(s, "D4", **{"from": frm, "to": to})
        excursion = []
        for uris in d4.humidity_series:
            mins = sum(int((values(u, frm, to) > 75).sum()) for u in uris)
            excursion.append(mins)
        d4["humidity_minutes_over_75"] = excursion
        d4["score"] = d4.alarms + d4.humidity_minutes_over_75
        d4 = d4.sort_values(["score", "alarms"], ascending=False).drop(columns=["humidity_series"])
        out += section("D4", d4, [
            f"- Crater spike: {(pd.to_datetime(crater.t).dt.floor('h') == spike).sum()} craters in the hour from "
            f"{spike:%d %b %H:%M}; window = 2 h before the spike hour to its end.",
            "- Ranking = non-duplicate alarms on the upstream asset or anything partOf it + minutes of RH > 75 %. "
            "The AHU for booth B is first: humidity alarm flood and RH excursion, i.e. WO 4102963 "
            "(humidifier valve stuck open)."], {"from": frm, "to": to})

        d5 = run(s, "D5")
        out += section("D5", d5, [
            f"- Lot id scope: {d5.vehicles.sum():,} vehicles. But the 4 Sep fitting session had 0 door leaks while "
            "8–10 Sep had all of them (Part B finding: the lot id was not updated at T2-01).",
            f"- Refined recall scope (fitted from 8 Sep): {d5[d5.fitted_on >= pd.Timestamp('2026-09-08').date()].vehicles.sum():,} "
            "vehicles – the lot id alone would recall 293 good cars."])

        d6 = run(s, "D6")
        d6b = run(s, "D6b")
        q = build_queue()
        out += section("D6", d6, [f"- Outside the graph, waiting in the review app: "
                                  + ", ".join(f"{k} {v}" for k, v in q.kind.value_counts().items()) + "."])
        mix = ", ".join(f"{r.relationship}/{r.method} {r.edges:,}" for r in d6b.itertuples())
        out += section("D6b", d6b, [f"- Edges below 0.8: {mix or 'none'}. Inferred RFID passages right after a buffer "
                                    "(P-INS, T1-01) get 0.60 because their validated timing error is large "
                                    "(see report 10); every matcher link in the graph is at or above its "
                                    "auto-accept threshold."])

        w = problem_windows()
        p7 = {"lot": "WS-260904-B", "lot_from": datetime(2026, 9, 8), "sealer": "DDN1-PNT-SL-ST02-SR03",
              "seal_from": w["seal"][0], "seal_to": w["seal"][1], "robot": "DDN1-BIW-L2-ST04-RB07",
              "weld_from": w["weld"][0], "weld_to": w["weld"][1]}
        d7 = run(s, "D7", **p7)
        out += section("D7", d7, [
            "- Windows are the out-of-spec periods found in Part B (re-computed from the time series).",
            "- `not_caught` is the field-risk number: cars that were exposed but never showed the defect at "
            "inspection. For the cold-weld window that is expected (only some welds are undersize and the "
            "chisel test samples); for the door-seal lot it means the shower test did not see every bad seal."],
            {k: v for k, v in p7.items()})

    path = REPORTS / "12_graph_queries.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"7 queries -> {path}")


if __name__ == "__main__":
    main()
