"""Part D - load the knowledge graph into Neo4j.

Design
- The ontology YAML is the contract: labels, keys, constraints and indexes come from it,
  and after loading every relationship is checked against its allowed endpoints.
- Containers vs views (Cognite): a label + its constraints/indexes is the container;
  the views (Maintenance, Quality, Traceability) are read patterns in ddn.queries.
- Every relationship is written through `edges()`, which refuses rows without the five
  provenance fields: source_system, method, confidence, created_at, status.
- Only approved links are loaded: auto-accepted ones and engineer decisions
  (method=engineer, confidence 1.0). The review band and backlog stay out of the graph.
- Time-series values stay in Parquet; a TimeSeries node holds `store_uri` plus a cached
  latest value.

Run (Neo4j must be up: `docker compose up -d`):
    python -m ddn.graph        (writes reports/11_graph_load.md)
Connection: NEO4J_URI (bolt://localhost:7687), NEO4J_USER (neo4j), NEO4J_PASSWORD (ddn-plant-2026)
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
from neo4j import GraphDatabase

from .config import REPORTS, ROOT, STAGING
from .load import load
from .ontology import load_ontology
from .review import engineer_labels, load_decisions

BATCH = 10_000
NOW = datetime.now().replace(microsecond=0)
STRUCTURAL = {"Site": "Site", "Shop": "Shop", "Area": "Line", "Line": "Line", "Station": "Station"}
DEFECT_FAMILY = {"BW": "weld", "BP": "panel", "BG": "gap/flush", "BD": "body dent", "PD": "paint",
                 "WL": "water leak", "AU": "audit", "AL": "alignment"}
PROVENANCE = ("source_system", "method", "confidence", "created_at", "status")


def driver():
    return GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                                auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "ddn-plant-2026")))


def neo4j_available(wait_s: int = 120) -> bool:
    """True once Neo4j accepts a connection (it needs ~20-60 s after `docker compose up`)."""
    deadline = time.time() + wait_s
    while True:
        try:
            with driver() as d:
                d.verify_connectivity()
            return True
        except Exception:
            if time.time() > deadline:
                return False
            time.sleep(3)


# ------------------------------------------------------------------ helpers
def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts the Neo4j driver accepts. Vectorised: object dtype turns numpy
    ints/floats/bools into Python ones and Timestamps (datetime subclasses) pass through; NaN/NaT -> None.
    (A per-value Python conversion was the bottleneck: 11 M values for 1.1 M edges.)"""
    out = df.astype(object)
    return out.where(df.notna(), None).to_dict("records")


def run_batches(session, cypher: str, rows: list[dict]) -> int:
    for i in range(0, len(rows), BATCH):
        session.run(cypher, rows=rows[i:i + BATCH]).consume()
    return len(rows)


def nodes(session, label: str, key: str, df: pd.DataFrame) -> int:
    return run_batches(session, f"UNWIND $rows AS r MERGE (n:{label} {{{key}: r.{key}}}) SET n += r", records(df))


def edges(session, rel: str, df: pd.DataFrame, src: tuple[str, str, str], dst: tuple[str, str, str],
          props: list[str] = ()) -> int:
    """src/dst = (label or 'Asset', node key property, dataframe column). Provenance is mandatory."""
    missing = [p for p in PROVENANCE if p not in df.columns or df[p].isna().any()]
    if missing:
        raise ValueError(f"{rel}: provenance missing or empty: {missing}")
    (sl, sk, sc), (dl, dk, dc) = src, dst
    cols = list(dict.fromkeys([sc, dc, *props, *PROVENANCE, *(["evidence"] if "evidence" in df else []),
                               *(["model_version"] if "model_version" in df else [])]))
    set_props = ", ".join(f"{c}: r.{c}" for c in cols if c not in (sc, dc))
    cypher = (f"UNWIND $rows AS r MATCH (a:{sl} {{{sk}: r.{sc}}}) MATCH (b:{dl} {{{dk}: r.{dc}}}) "
              f"CREATE (a)-[:{rel} {{{set_props}}}]->(b)")
    return run_batches(session, cypher, records(df[cols]))


def prov(df: pd.DataFrame, source: str, method, confidence, status: str = "approved", **extra) -> pd.DataFrame:
    return df.assign(source_system=source, method=method, confidence=confidence, created_at=NOW, status=status,
                     **extra)


# ----------------------------------------------------------- build frames
def asset_nodes(assets: pd.DataFrame, stations: pd.DataFrame, aliases: dict[str, list[str]]) -> pd.DataFrame:
    a = assets.copy()
    kind = a.set_index("functional_location").asset_type
    def label(r):
        if r.asset_type in STRUCTURAL:
            return STRUCTURAL[r.asset_type]
        parent_type = kind.get(r.parent_fl)
        last = r.functional_location.split("-")[-1]
        return "Component" if parent_type not in STRUCTURAL and parent_type is not None and not re.search(r"\d", last) \
            else "Equipment"
    a["label"] = a.apply(label, axis=1)
    st = stations.set_index("fl")
    a["mes_code"] = a.functional_location.map(st.mes_station)
    a["sequence"] = a.functional_location.map(st.sequence)
    a["rfid_reader"] = "RD-" + a.mes_code
    a["aliases"] = a.functional_location.map(lambda f: sorted(set(aliases.get(f, []))) or None)
    a = a.rename(columns={"functional_location": "fl", "cmms_equipment_no": "sap_equipment_no"})
    a["iso14224_class"] = a.asset_type
    a["code"] = a.fl.str.split("-").str[-1]
    a["install_date"] = pd.to_datetime(a.install_date).dt.date
    return a


def timeseries_nodes(tags: pd.DataFrame) -> pd.DataFrame:
    ts = pd.read_parquet(STAGING / "timeseries")
    last = ts.sort_values("timestamp").groupby("tag_name", observed=True).tail(1).set_index("tag_name")
    t = tags.rename(columns={"tag_name": "tag", "isa51_code": "isa51_code"}).copy()
    has = t.tag.isin(last.index)
    t["store_uri"] = np.where(has, "parquet:data/staging/timeseries/tag_name=" + t.tag, None)
    t["latest_value"] = t.tag.map(last.value)
    t["latest_at"] = t.tag.map(last.timestamp)
    return t[["tag", "source_system", "description", "unit", "unit_canonical", "isa51_code", "signal",
              "store_uri", "latest_value", "latest_at", "legacy_name"]]


def link_method(final: pd.DataFrame, rules: pd.DataFrame, key: str) -> pd.Series:
    """Which method produced an auto-accepted link: rules agreed -> rule / source_key, otherwise ml."""
    r = rules.set_index(key)
    same = final.set_index(key).functional_location == r.functional_location.reindex(final[key]).values
    rule_m = r.method.reindex(final[key]).values
    m = np.where(same & np.isin(rule_m, ["exact", "alias", "relocation", "fl_text", "name"]), "rule",
                 np.where(same & (rule_m == "eq_no"), "source_key", "ml"))
    return pd.Series(m, index=final.index)


def approved_links(kind: str, key: str, rules_file: str) -> pd.DataFrame:
    """Auto-accepted ML links + engineer decisions (which override the model)."""
    links = pd.read_parquet(STAGING / f"links_{key}.parquet")
    rules = pd.read_parquet(STAGING / rules_file)
    auto = links[links.band == "auto_accept"].copy()
    auto["method"] = link_method(auto, rules, key).values
    eng = engineer_labels(kind)
    decided = set(load_decisions().query("kind == @kind").record)
    auto = auto[~auto[key].isin(decided)]
    eng_df = pd.DataFrame({key: list(eng), "functional_location": list(eng.values()), "confidence": 1.0,
                           "method": "engineer"})
    return pd.concat([auto[[key, "functional_location", "confidence", "method"]], eng_df], ignore_index=True)


# --------------------------------------------------------------------- load
def load_graph() -> dict:
    o = load_ontology()
    assets = pd.read_parquet(STAGING / "assets.parquet")
    stations = pd.read_parquet(STAGING / "stations.parquet")
    tags = pd.read_parquet(STAGING / "tags.parquet")
    docs = pd.read_parquet(STAGING / "doc_mentions.parquet")
    alarms = pd.read_parquet(STAGING / "alarms.parquet")
    wof = pd.read_parquet(STAGING / "wo_failure_modes.parquet")
    wo_raw = load("maintenance_work_orders.csv")
    decisions = load_decisions()

    aliases: dict[str, list[str]] = {}
    for r in docs[docs.target_kind == "asset"].itertuples():
        aliases.setdefault(r.target, []).append(r.label)
    for fl, g in alarms.dropna(subset=["functional_location"]).groupby("functional_location"):
        aliases.setdefault(fl, []).extend(g.source.unique()[:4])

    counts: dict[str, int] = {}
    t0 = time.time()
    with driver() as drv, drv.session() as s:
        # clear in small transactions: relationships first, so no single transaction holds a million deletes
        s.run("MATCH ()-[r]->() CALL (r) { DELETE r } IN TRANSACTIONS OF 50000 ROWS").consume()
        s.run("MATCH (n) CALL (n) { DELETE n } IN TRANSACTIONS OF 50000 ROWS").consume()
        # ---- containers: uniqueness constraints on every key + range indexes from the ontology
        for n in o.nodes.values():
            s.run(f"CREATE CONSTRAINT {n.name.lower()}_key IF NOT EXISTS FOR (x:{n.name}) REQUIRE x.{n.key} IS UNIQUE").consume()
        for idx in o.containers["indexes"]:
            if "rel" in idx:
                s.run(f"CREATE INDEX {idx['rel']}_{idx['property']} IF NOT EXISTS FOR ()-[r:{idx['rel']}]-() "
                      f"ON (r.{idx['property']})").consume()
            elif idx["kind"] == "range":
                s.run(f"CREATE INDEX {idx['label'].lower()}_{idx['property']} IF NOT EXISTS FOR (x:{idx['label']}) "
                      f"ON (x.{idx['property']})").consume()
        for lbl in ("Site", "Shop", "Line", "Station", "Equipment", "Component"):
            s.run(f"CREATE INDEX {lbl.lower()}_asset IF NOT EXISTS FOR (x:{lbl}) ON (x.fl)").consume()

        # ---- asset hierarchy (every asset also gets the generic :Asset label for lookups by fl)
        an = asset_nodes(assets, stations, aliases)
        cols = ["fl", "name", "asset_type", "iso14224_class", "sap_equipment_no", "manufacturer", "model",
                "install_date", "criticality", "description", "mes_code", "sequence", "rfid_reader", "aliases", "code"]
        for lbl, g in an.groupby("label"):
            counts[lbl] = run_batches(s, f"UNWIND $rows AS r MERGE (n:{lbl}:Asset {{fl: r.fl}}) SET n += r",
                                      records(g[cols]))
        s.run("CREATE CONSTRAINT asset_key IF NOT EXISTS FOR (x:Asset) REQUIRE x.fl IS UNIQUE").consume()
        po = an[an.parent_fl.notna()].rename(columns={"parent_fl": "parent"})
        reloc = po.description.fillna("").str.extract(r"Relocated from L(\d) ST(\d+) \(ex R(\d+)\) in ([A-Z][a-z]{2})-(\d{4})")
        po["valid_from"] = None
        po["valid_to"] = None
        moved = reloc[0].notna()
        po.loc[moved, "valid_from"] = pd.to_datetime("1 " + reloc[3] + " " + reloc[4]).loc[moved].dt.to_pydatetime()
        hist = po[moved].copy()                       # where the robot was before the move
        hist["parent"] = "DDN1-BIW-L" + reloc[0][moved] + "-ST" + reloc[1][moved].str.zfill(2)
        hist["valid_to"], hist["valid_from"] = hist.valid_from, None
        hist["evidence"] = "asset description: " + hist.description
        po["evidence"] = np.where(po.parent_repaired, "parent repaired from FL path", "SAP parent")
        part_of = pd.concat([prov(po, "SAP_PM", np.where(po.parent_repaired, "rule", "source_key"),
                                  np.where(po.parent_repaired, 0.95, 1.0)),
                             prov(hist, "SAP_PM", "rule", 0.95)], ignore_index=True)
        counts["partOf"] = edges(s, "partOf", part_of, ("Asset", "fl", "fl"), ("Asset", "fl", "parent"),
                                 ["valid_from", "valid_to"])

        # ---- time series + tag links
        counts["TimeSeries"] = nodes(s, "TimeSeries", "tag", timeseries_nodes(tags))
        tl = approved_links("tag", "tag_name", "tag_matches_rules.parquet")
        counts["hasTimeSeries"] = edges(s, "hasTimeSeries", prov(tl, "PIPELINE", tl.method, tl.confidence,
                                        model_version="match_ml-v1"),
                                        ("Asset", "fl", "functional_location"), ("TimeSeries", "tag", "tag_name"))

        # ---- work orders, failure modes
        wo = wo_raw.merge(wof[["wo_number", "iso14224", "evidence"]], on="wo_number", how="left")
        counts["WorkOrder"] = nodes(s, "WorkOrder", "wo_number",
                                    wo[["wo_number", "wo_type", "priority", "created_at", "closed_at", "short_text",
                                        "long_text", "technician", "failure_code"]])
        wl = approved_links("workorder", "wo_number", "wo_matches_rules.parquet")
        counts["hasWorkOrder"] = edges(s, "hasWorkOrder", prov(wl, "PIPELINE", wl.method, wl.confidence,
                                       model_version="match_ml-v1"),
                                       ("Asset", "fl", "functional_location"), ("WorkOrder", "wo_number", "wo_number"))
        from .workorders import ISO14224
        fm = pd.DataFrame({"code": list(ISO14224), "name": list(ISO14224.values()), "standard": "ISO 14224"})
        counts["FailureMode"] = nodes(s, "FailureMode", "code", fm)
        rf = wo.dropna(subset=["iso14224"])
        counts["reportsFailure"] = edges(s, "reportsFailure", prov(rf, "PIPELINE", "rule", 0.9),
                                         ("WorkOrder", "wo_number", "wo_number"), ("FailureMode", "code", "iso14224"))

        # ---- documents
        files = sorted((ROOT / "docs" / "source_pack" / "documents").rglob("*.pdf"))
        dn = pd.DataFrame([{"doc_id": "-".join(p.stem.split("_")[0].split("-")[:3 if p.stem.startswith("MAN") else 4])
                            if p.parent.name in ("drawings", "manuals") else p.stem,
                            "title": p.stem.split("_", 1)[-1].replace("_", " "),
                            "kind": {"drawings": "drawing", "manuals": "manual"}.get(p.parent.name, "document"),
                            "path": str(p.relative_to(ROOT)).replace("\\", "/"), "ocr": "SCANNED" in p.stem}
                           for p in files])
        counts["Document"] = nodes(s, "Document", "doc_id", dn)
        dm = docs[docs.target.notna()].copy()
        eng_doc = decisions[decisions.kind == "document"]
        dm["item_id"] = "doc:" + dm.doc_id + ":" + dm.page.astype(str) + ":" + dm.label + ":" + dm.target
        dec = eng_doc.set_index("item_id").astype(object)
        keep = (dm.confidence >= 0.90) | dm.item_id.isin(dec.index[dec.decision.isin(["approve", "correct"])])
        dm = dm[keep & ~dm.item_id.isin(dec.index[dec.decision == "reject"])]
        engineer = dm.item_id.isin(dec.index)
        dm["evidence"] = "read by " + dm.method                 # text layer / ocr / ocr_corrected / model table
        dm["method"] = np.where(engineer, "engineer", "rule")
        dm["confidence"] = np.where(engineer, 1.0, dm.confidence)
        corrected = dm.item_id.map(dec.functional_location).astype(object)
        dm["target"] = np.where(engineer & corrected.notna(), corrected, dm.target)
        dm = prov(dm, "DOCUMENTS", dm.method, dm.confidence)
        counts["mentionedIn(asset)"] = edges(s, "mentionedIn", dm[dm.target_kind == "asset"],
                                             ("Asset", "fl", "target"), ("Document", "doc_id", "doc_id"), ["page", "label"])
        counts["mentionedIn(tag)"] = edges(s, "mentionedIn", dm[dm.target_kind == "timeseries"],
                                           ("TimeSeries", "tag", "target"), ("Document", "doc_id", "doc_id"),
                                           ["page", "label"])

        # ---- alarms
        counts["Alarm"] = nodes(s, "Alarm", "event_id",
                                alarms.rename(columns={"source": "source_raw"})[
                                    ["event_id", "event_time", "event_type", "code", "message", "priority",
                                     "duration_s", "source_raw", "is_duplicate", "manual_meaning"]])
        ra = alarms.dropna(subset=["functional_location"])
        counts["raisedBy"] = edges(s, "raisedBy", prov(ra, "ALARMS", np.where(ra.method == "mes_station", "rule", "rule"),
                                                       ra.confidence, evidence="source " + ra.source),
                                   ("Alarm", "event_id", "event_id"), ("Asset", "fl", "functional_location"))

        # ---- process flow
        f = pd.read_parquet(STAGING / "feeds.parquet")
        counts["feeds"] = edges(s, "feeds", prov(f, np.where(f.relation == "process_flow", "MES", "PIPELINE"),
                                                 "derived", 0.95),
                                ("Asset", "fl", "from_fl"), ("Asset", "fl", "to_fl"), ["relation"])

        # ---- vehicles, passages, equipment, torque, parts, defects
        v = load("vehicles.csv")
        counts["Vehicle"] = nodes(s, "Vehicle", "vin", v)
        pas = pd.read_parquet(STAGING / "passages_full.parquet")
        pas["reader_id"] = np.where(pas.inferred, None, "RD-" + pas.mes_station)
        pas = prov(pas, "MES", np.where(pas.inferred, "inferred", "source_key"),
                   np.where(~pas.inferred, 0.99, np.where(pas.uncertainty_min <= 2.4, 0.85, 0.60)))
        counts["passedThrough"] = edges(s, "passedThrough", pas, ("Vehicle", "vin", "vin"), ("Asset", "fl", "fl"),
                                        ["passed_at", "reader_id", "inferred", "uncertainty_min", "mes_station"])
        pb = pd.read_parquet(STAGING / "processed_by.parquet")
        pb = prov(pb, np.where(pb.method == "torque_result", "TOOL_CTRL", "MES"),
                  np.where(pb.method == "torque_result", "source_key", np.where(pb.inferred, "inferred", "derived")),
                  pb.confidence)
        counts["processedBy"] = edges(s, "processedBy", pb, ("Vehicle", "vin", "vin"), ("Asset", "fl", "fl"),
                                      ["start", "end", "inferred"])

        tools = pd.read_parquet(STAGING / "tools.parquet")
        counts["Tool"] = nodes(s, "Tool", "tool_id", tools[["tool_id", "kind"]])
        tt = tools.dropna(subset=["controller_fl"])
        counts["partOf(tool)"] = edges(s, "partOf", prov(tt, "TOOL_CTRL", "rule", 0.97, evidence="TCnn = NRnn controller"),
                                       ("Tool", "tool_id", "tool_id"), ("Asset", "fl", "controller_fl"))
        tq = load("torque_results.csv.gz")
        counts["TorqueResult"] = nodes(s, "TorqueResult", "result_id",
                                       tq[["result_id", "joint_id", "program", "torque_nm", "angle_deg", "torque_min",
                                           "torque_max", "status", "attempt", "timestamp"]])
        counts["hasTorqueResult"] = edges(s, "hasTorqueResult", prov(tq, "TOOL_CTRL", "source_key", 1.0),
                                          ("Vehicle", "vin", "vin"), ("TorqueResult", "result_id", "result_id"))
        counts["tightenedBy"] = edges(s, "tightenedBy", prov(tq, "TOOL_CTRL", "source_key", 1.0),
                                      ("TorqueResult", "result_id", "result_id"), ("Tool", "tool_id", "tool_id"))

        pl = pd.read_parquet(STAGING / "part_lots.parquet")
        counts["Part"] = nodes(s, "Part", "part_uid", pl[["part_uid", "part_no", "part_desc", "supplier"]])
        lots = (pl.groupby("lot_id").agg(supplier=("supplier", "first"), part_no=("part_no", "first"),
                                         produced_from=("produced_from", "first"), produced_to=("produced_to", "first"),
                                         press_line=("press_line", "first"), die_id=("die_id", "first"),
                                         first_fitted=("fitted_at", "min"), last_fitted=("fitted_at", "max"),
                                         vehicles=("vin", "nunique")).reset_index())
        counts["SupplierLot"] = nodes(s, "SupplierLot", "lot_id", lots)
        counts["containsPart"] = edges(s, "containsPart", prov(pl.rename(columns={"fitted_mes_station": "fitted_station"}),
                                                               "MES", "source_key", 1.0),
                                       ("Vehicle", "vin", "vin"), ("Part", "part_uid", "part_uid"),
                                       ["fitted_at", "fitted_station"])
        counts["fromLot"] = edges(s, "fromLot", prov(pl, "MES", "source_key", 1.0),
                                  ("Part", "part_uid", "part_uid"), ("SupplierLot", "lot_id", "lot_id"))

        d = load("quality_defects.csv")
        d["defect_family"] = d.defect_code.str[:2].map(DEFECT_FAMILY)
        counts["Defect"] = nodes(s, "Defect", "defect_id", d.drop(columns=["vin", "inspection_point"]))
        counts["hasDefect"] = edges(s, "hasDefect", prov(d, "QMS", "source_key", 1.0),
                                    ("Vehicle", "vin", "vin"), ("Defect", "defect_id", "defect_id"))
        d["station_fl"] = d.inspection_point.map(stations.set_index("mes_station").fl)
        counts["detectedAt"] = edges(s, "detectedAt", prov(d, "QMS", "rule", 0.99, evidence="inspection point " + d.inspection_point),
                                     ("Defect", "defect_id", "defect_id"), ("Asset", "fl", "station_fl"))
    counts["_seconds"] = round(time.time() - t0)
    return counts


# --------------------------------------------------------------- validation
def validate_graph() -> dict:
    """Checks a reviewer would ask for: provenance everywhere, endpoints as the ontology allows."""
    o = load_ontology()
    out = {}
    with driver() as drv, drv.session() as s:
        out["nodes"] = {r["l"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND [l IN labels(n) WHERE l <> 'Asset'] AS l RETURN l, count(*) AS n ORDER BY n DESC")}
        out["rels"] = {r["t"]: r["n"] for r in s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY n DESC")}
        out["missing_provenance"] = s.run(
            "MATCH ()-[r]->() WHERE r.source_system IS NULL OR r.method IS NULL OR r.confidence IS NULL "
            "OR r.created_at IS NULL OR r.status IS NULL RETURN count(r) AS n").single()["n"]
        bad = {}
        present = set(out["rels"])
        for e in (e for e in o.edges.values() if e.name in present):
            n = s.run(f"MATCH (a)-[r:{e.name}]->(b) WHERE none(l IN labels(a) WHERE l IN $f) "
                      f"OR none(l IN labels(b) WHERE l IN $t) RETURN count(r) AS n", f=e.from_, t=e.to).single()["n"]
            if n:
                bad[e.name] = n
        out["ontology_violations"] = bad
        enums = {k: o.provenance[k]["values"] for k in ("method", "source_system", "status")}
        out["enum_violations"] = {k: [r["v"] for r in s.run(f"MATCH ()-[r]->() WHERE NOT r.{k} IN $ok "
                                                             f"RETURN DISTINCT r.{k} AS v", ok=ok)]
                                  for k, ok in enums.items()}
        out["enum_violations"] = {k: v for k, v in out["enum_violations"].items() if v}
        out["by_method"] = [dict(r) for r in s.run(
            "MATCH ()-[r]->() RETURN r.method AS method, count(*) AS edges, round(avg(r.confidence), 3) AS avg_conf "
            "ORDER BY edges DESC")]
    return out


def main() -> None:
    counts = load_graph()
    v = validate_graph()
    total_n, total_r = sum(v["nodes"].values()), sum(v["rels"].values())
    out = ["# Part D – Knowledge graph load (Neo4j)", "",
           f"Generated by `python -m ddn.graph`. Ontology v{load_ontology().version}. "
           f"Loaded in {counts['_seconds']} s: **{total_n:,} nodes, {total_r:,} relationships**.", "",
           "## Checks", "",
           f"- Relationships without full provenance (source_system, method, confidence, created_at, status): "
           f"**{v['missing_provenance']}**",
           f"- Relationships whose endpoints break the ontology: **{sum(v['ontology_violations'].values())}** "
           f"{v['ontology_violations'] or ''}",
           f"- Provenance values outside the ontology's allowed lists: **{v['enum_violations'] or 'none'}**",
           "- Only approved links are loaded: auto-accepted by the matcher, or decided by an engineer "
           "(`data/review/decisions.csv`). The review band stays in the review app.", "",
           "## Nodes", "", "| Label | Count |", "|---|---:|"]
    out += [f"| {k} | {n:,} |" for k, n in v["nodes"].items()]
    out += ["", "## Relationships", "", "| Type | Count |", "|---|---:|"]
    out += [f"| {k} | {n:,} |" for k, n in v["rels"].items()]
    out += ["", "## Relationships by method (provenance)", "", "| Method | Edges | Avg confidence |", "|---|---:|---:|"]
    out += [f"| {r['method']} | {r['edges']:,} | {r['avg_conf']} |" for r in v["by_method"]]
    path = REPORTS / "11_graph_load.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"graph: {total_n:,} nodes, {total_r:,} rels in {counts['_seconds']} s; missing provenance "
          f"{v['missing_provenance']}; ontology violations {v['ontology_violations']}; enum violations "
          f"{v['enum_violations']} -> {path}")


if __name__ == "__main__":
    main()
