"""The two stories of the demo video, printed step by step.

    python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV     one robot tag: raw name -> graph node
    python -m ddn.demo vin                                one VIN traced end to end (default: a cold-weld car)
    python -m ddn.demo vin MDDA5XK0XD004375

The tag story uses the staging files (parse, match) and the graph (node, edges, provenance).
The VIN story is graph-only: every line is one Cypher query result.
"""
from __future__ import annotations

import sys

import pandas as pd

from .config import STAGING
from .graph import driver
from .tags import parse_tag


def h(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))


def tag_story(tag: str) -> None:
    tags = pd.read_parquet(STAGING / "tags.parquet").set_index("tag_name")
    if tag not in tags.index:
        raise SystemExit(f"unknown tag {tag}")
    t = tags.loc[tag]
    h("1. Raw record in the historian tag list")
    print(f"tag {tag}  source={t.source_system}  unit={t.unit}  description={t.description}")
    h("2. Parsed (ddn.tags.parse_tag) and normalised")
    p = parse_tag(tag, t.source_system)
    print(f"shop={p['shop']} line={p['line']} equipment={p['equip']} signal={p['signal']} "
          f"-> ISA-5.1 code {t.isa51_code}, canonical unit {t.unit_canonical}")
    h("3. Matched to an asset (rules + LightGBM, ddn.match_ml)")
    link = pd.read_parquet(STAGING / "links_tag_name.parquet").set_index("tag_name").loc[tag]
    print(f"-> {link.functional_location}  confidence {link.confidence:.3f}  band {link.band}  method {link.method}")
    with driver() as d, d.session() as s:
        h("4. In the knowledge graph")
        for r in s.run("""MATCH (a:Asset)-[e:hasTimeSeries]->(t:TimeSeries {tag: $tag})
                          RETURN a.fl AS fl, a.name AS name, t.isa51_code AS isa, t.store_uri AS uri,
                                 e.source_system AS src, e.method AS method, e.confidence AS conf,
                                 e.status AS status, e.evidence AS evidence""", tag=tag):
            print(f"({r['fl']} '{r['name']}')-[:hasTimeSeries]->(:TimeSeries {tag})")
            print(f"   provenance: source={r['src']} method={r['method']} confidence={r['conf']:.3f} "
                  f"status={r['status']} evidence={r['evidence']}")
            print(f"   values are not in the graph: store_uri = {r['uri']}")
        h("5. Its context: hierarchy, work orders, anomalies")
        for r in s.run("""MATCH (t:TimeSeries {tag: $tag})<-[:hasTimeSeries]-(a:Asset)
                          MATCH p = (a)-[:partOf*1..5]->(:Site)
                          RETURN [n IN nodes(p) | n.fl] AS path LIMIT 1""", tag=tag):
            print("partOf: " + " -> ".join(r["path"]))
        for r in s.run("""MATCH (t:TimeSeries {tag: $tag})-[:hasEvent]->(e:AnomalyEvent)
                          RETURN e.anomaly_id AS id, e.judged AS j, e.start AS s, e.confirming_wo AS wo""", tag=tag):
            print(f"anomaly {r['id']} from {r['s']}: {r['j']}, confirmed by WO {r['wo']}")
        n = s.run("""MATCH (t:TimeSeries {tag: $tag})<-[:hasTimeSeries]-(a:Asset)-[:hasWorkOrder]->(w)
                     RETURN count(w) AS n""", tag=tag).single()["n"]
        print(f"{n} work orders on the same asset")


DEFAULT_VIN_QUERY = """MATCH (v:Vehicle)-[:hasDefect]->(d:Defect {defect_code: 'BW-017'})-[:causedBy]->(:AnomalyEvent)
                       RETURN v.vin AS vin ORDER BY vin LIMIT 1"""


def vin_story(vin: str | None) -> None:
    with driver() as d, d.session() as s:
        vin = vin or s.run(DEFAULT_VIN_QUERY).single()["vin"]
        h(f"Vehicle {vin}")
        v = s.run("MATCH (v:Vehicle {vin: $vin}) RETURN v", vin=vin).single()["v"]
        print(f"model {v['model_code']} {v['model_desc']}, colour {v['color']}, body start {v['body_start_at']}")
        h("1. Route: stations passed (MES / RFID; inferred = missed read filled from takt time)")
        rows = s.run("""MATCH (v:Vehicle {vin: $vin})-[p:passedThrough]->(st)
                        RETURN st.fl AS fl, p.passed_at AS t, p.inferred AS inf ORDER BY t""", vin=vin).data()
        for r in rows[:6] + ([{"fl": f"... {len(rows) - 12} more ...", "t": "", "inf": False}] if len(rows) > 12 else []) + rows[-6:]:
            print(f"  {str(r['t'])[:19]:19}  {r['fl']}{'  (inferred)' if r['inf'] else ''}")
        h("2. Equipment that worked on it (processedBy)")
        for r in s.run("""MATCH (v:Vehicle {vin: $vin})-[p:processedBy]->(e:Asset)
                          WHERE e.asset_type IN ['Robot', 'SealerRobot', 'Press', 'PaintRobot', 'OvenZone']
                          RETURN e.asset_type AS type, collect(e.fl)[..6] AS fls, count(*) AS n ORDER BY type""", vin=vin):
            print(f"  {r['type']:12} {r['n']:3}  {', '.join(r['fls'])}{' ...' if r['n'] > 6 else ''}")
        h("3. Torque results and the tool used")
        r = s.run("""MATCH (v:Vehicle {vin: $vin})-[:hasTorqueResult]->(t)-[:tightenedBy]->(tool)
                     RETURN count(t) AS n, sum(CASE WHEN t.status <> 'OK' THEN 1 ELSE 0 END) AS nok,
                            collect(DISTINCT tool.tool_id)[..4] AS tools""", vin=vin).single()
        print(f"  {r['n']} joints, {r['nok']} not OK, tools {', '.join(r['tools'])}")
        h("4. Parts and supplier lots")
        for r in s.run("""MATCH (v:Vehicle {vin: $vin})-[c:containsPart]->(p)-[:fromLot]->(l)
                          RETURN p.part_no AS part, l.lot_id AS lot, l.supplier AS sup ORDER BY part""", vin=vin):
            print(f"  {r['part']:18} lot {r['lot']:16} {r['sup']}")
        h("5. Defects, and what the graph says caused them")
        for r in s.run("""MATCH (v:Vehicle {vin: $vin})-[:hasDefect]->(d)
                          OPTIONAL MATCH (d)-[:detectedAt]->(st)
                          OPTIONAL MATCH (d)-[c:causedBy]->(cause)
                          OPTIONAL MATCH (eq:Asset)-[:hasEvent]->(cause)
                          OPTIONAL MATCH (w:WorkOrder {wo_number: cause.confirming_wo})
                          RETURN d.defect_id AS id, d.defect_code AS code, d.defect_desc AS desc, st.fl AS at,
                                 coalesce(cause.anomaly_id, cause.lot_id) AS cause, eq.fl AS eq, c.method AS m,
                                 c.confidence AS conf, c.status AS status, w.wo_number AS wo, w.short_text AS wo_text""",
                       vin=vin):
            print(f"  {r['id']} {r['code']} {r['desc']} at {r['at']}")
            if r["cause"]:
                print(f"     causedBy {r['cause']} on {r['eq'] or '-'}  ({r['m']}, confidence {r['conf']}, {r['status']})")
            if r["wo"]:
                print(f"     fixed by WO {r['wo']}: {r['wo_text']}")
        h("6. Anomalies the car was exposed to")
        for r in s.run("""MATCH (v:Vehicle {vin: $vin})-[x:exposedTo]->(e)<-[:hasEvent]-(eq:Asset)
                          RETURN e.anomaly_id AS id, eq.fl AS fl, e.judged AS j, x.basis AS basis""", vin=vin):
            print(f"  {r['id']} on {r['fl']}: {r['j']} (exposed because: {r['basis']})")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["tag"]:
        tag_story(args[1] if len(args) > 1 else "DDN1_BIW_L2_R07_WELDCUR.PV")
    elif args[:1] == ["vin"]:
        vin_story(args[1] if len(args) > 1 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
