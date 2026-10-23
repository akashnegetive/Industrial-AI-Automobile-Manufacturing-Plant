"""Part B.3 - identity schemes: how the same asset is named in each system.

Two outputs:
1. The naming *pattern* per system (from the plant overview + what the data shows).
2. Worked examples: for six real assets, the actual strings found in each file.
   Examples are pulled from the data with search patterns, so the table is
   evidence, not just documentation. Drawing labels come from the PDFs we read.

Run:  python -m ddn.identity     (writes reports/03_identity_schemes.md)
"""
from __future__ import annotations

import pandas as pd

from .config import REPORTS
from .load import load

SCHEMES = [
    # system, key column, pattern, example, quirks
    ("SAP PM asset master", "functional_location", "DDN1-<shop>-<line>-<stn>-<equip>[-<comp>]",
     "DDN1-BIW-L2-ST04-RB07", "Canonical key. Die ids contain '-' (DDN1-PRS-DIES-D-BSO-LH-03)."),
    ("SAP PM asset master", "cmms_equipment_no", "8-digit number, 1000xxxx", "10007731",
     "Blank for structural levels (site/shop/line/station)."),
    ("PI Historian", "tag_name", "DDN1_<shop>_<line>_<equip>_<signal>.PV", "DDN1_BIW_L2_R07_WELDCUR.PV",
     "No station in name; R07 not RB07; typos DD1_/DN1_; relocated robot keeps old name."),
    ("WinCC SCADA", "tag_name", "PaintShop-<area>-<equip>-<signal>", "PaintShop-Oven2-Z3-Temp",
     "Area spelled Oven2/OVN2/Ovn02, AHU/AirHandling; deg F."),
    ("S7 legacy OPC", "tag_name", "<shop>.<line>.<equip>.<signal>", "PRS.PL1.PR1.TON",
     "Sub-units glued to equipment: PR1HOL, PR2LUB."),
    ("MES tags", "tag_name", "FA_<line>_<equip>_<signal>", "FA_FN1_NR14_TQLAST", "Typos F_TR1, F_AFN1."),
    ("MES stations / RFID", "mes_station, reader_id", "<line><n>-<nn>, RD-<station>", "B2-04, RD-B2-04",
     "Own numbering: B2 = BIW L2, SLR-2 = sealer cell 2, F1 = FN1. No FL link."),
    ("Tool controllers", "tool_id", "TCnn (= nutrunner NRnn), HW-07", "TC14",
     "Channel number equals nutrunner number; HW-07 is a hand wrench."),
    ("Drawings", "labels", "Line-coded numbers: RB-2nn, WG-2nn, TD-2.nn; ISA-5.1 TT-/TE-/MT-",
     "RB-207, TE-423, AHU-02, BNR-B3, HD-03",
     "RB-207 = L2 robot 07; AHU-02 = AHU of booth B (TC2); BNR-B3 = oven B zone 3."),
    ("Alarms", "source", "PLC object path, separator . _ /", "BIW_L2_ST04_RB07, BIW/L2/S4/RB07",
     "Separators vary; station S4 vs ST04; MES station codes for andon."),
    ("Work orders", "equipment_no, functional_location_text, short_text",
     "SAP no. (often blank/wrong), hand-typed FL fragment, free text",
     "'R7 gun tip dressing fail', 'L2 ST4 robo'", "Nicknames, Hinglish, missing line number."),
    ("Defects", "inspection_point", "MES station code of the inspection", "BIQ-1, EOL-WT",
     "Never the causing equipment."),
]

# Six assets across the four shops. Search patterns are regexes per source.
EXAMPLES = {
    "DDN1-BIW-L2-ST04-RB07": {
        "desc": "Spot-weld robot 07, Body Line 2",
        "tag": r"BIW_L2_R07_WELDCUR", "alarm": r"BIW.L2.S(?:T0)?4.RB07", "mes": "B2-04",
        "wo": r"\bR7\b|Rob 07|L2 ST4|robot 7|RB07", "drawing": "RB-207 / WG-207 (DWG-BIW-L2-001)"},
    "DDN1-BIW-L2-ST06-RB12": {
        "desc": "Robot 12, L2 - relocated from L1 ST03 (ex R05)",
        "tag": r"L1ST3_RB5_WELDCUR", "alarm": r"BIW.L2.S(?:T0)?6.RB12", "mes": "B2-06",
        "wo": r"\bR12\b|Rob 12|RB12", "drawing": "RB-212 'relocated from line 1 stn 1.03 (ex RB-105)'"},
    "DDN1-PNT-SL-ST02-SR03-DSP": {
        "desc": "Heated dispenser on sealer robot SR03",
        "tag": r"SL_SR03_NOZTEMP", "alarm": r"PNT.SL.S(?:T0)?2.SR03", "mes": "SLR-2",
        "wo": r"SR03|SR-03|Sealer robo 3", "drawing": "SR-03 / HD-03 / TE-221 (DWG-PNT-SL-201)"},
    "DDN1-PNT-AHU-AHUTC2-HUM": {
        "desc": "Humidifier of the air handling unit for topcoat booth B",
        "tag": r"AHUTC2-Rh", "alarm": r"PNT.AHU.AHUTC2", "mes": "TC-2 (booth it serves)",
        "wo": r"AHU TC2|AHU-02", "drawing": "AHU-02 / HUM-02 / MT-02 (DWG-PNT-AHU-301)"},
    "DDN1-PNT-OV2-Z3": {
        "desc": "Topcoat oven B (OV2), zone 3",
        "tag": r"(?i)PaintShop-(?:OVN2|Oven2|Ovn02)-Z3-Temp$", "alarm": r"PNT.OV2.Z3", "mes": "OV-2",
        "wo": r"Oven 2 zone 3|OV2 Z3", "drawing": "ZONE B3 / BNR-B3 / TE-423 (DWG-PNT-OV-402)"},
    "DDN1-ASM-FN1-ST03-NR14": {
        "desc": "DC nutrunner 14, wheel nuts LF/LR, final line",
        "tag": r"FN1_NR14_TQLAST", "alarm": r"ASM.FN1.S(?:T0)?3.NR14", "mes": "F1-03",
        "wo": r"NR14|DC tool 14|tool 14", "drawing": "DC-14, ctrl TC14 (DWG-ASM-FN1-501)", "tool": "TC14"},
}


def _first(series: pd.Series, pattern: str, n: int = 3) -> str:
    hits = series[series.str.contains(pattern, regex=True, na=False)].drop_duplicates()
    return ", ".join(f"`{h}`" for h in hits.head(n)) or "—"


def build_examples() -> pd.DataFrame:
    a = load("assets_cmms_export.csv").set_index("functional_location")
    t = load("historian_tag_list.csv")
    al = load("alarms_andon_events.csv")
    wo = load("maintenance_work_orders.csv")
    rows = []
    for fl, ex in EXAMPLES.items():
        rows.append({
            "Functional location (SAP)": f"`{fl}`",
            "SAP equipment no.": a.cmms_equipment_no.get(fl, "—"),
            "SAP name": a.name.get(fl, "—"),
            "Historian tag(s)": _first(t.tag_name, ex["tag"], 2),
            "Alarm source(s)": _first(al.source, ex["alarm"], 3),
            "MES station": ex["mes"] + (f", tool `{ex['tool']}`" if "tool" in ex else ""),
            "Drawing label": ex["drawing"],
            "Work-order text": _first(wo.short_text, ex["wo"], 2),
        })
    return pd.DataFrame(rows)


def to_markdown() -> str:
    out = ["# Part B.3 – Identity schemes", "",
           "Generated by `python -m ddn.identity`. The canonical key is the SAP functional location.", "",
           "## Naming pattern per system", "",
           "| System | Field | Pattern | Example | Quirks seen in the data |", "|---|---|---|---|---|"]
    out += [f"| {s} | `{f}` | `{p}` | `{e}` | {q} |" for s, f, p, e, q in SCHEMES]
    out += ["", "## Six assets, every identity (pulled from the data)", ""]
    ex = build_examples()
    for _, r in ex.iterrows():
        fl = r["Functional location (SAP)"].strip("`")
        out += [f"### {EXAMPLES[fl]['desc']}", "", "| System | Identity |", "|---|---|"]
        out += [f"| {k} | {v} |" for k, v in r.items()] + [""]
    out += ["*Work-order text is a plain text search: 'R7' does not say which line, so some hits may belong to "
            "robot 7 on L1 or L3. Resolving that is the Part C matcher's job.*", "", "## Mapping rules this implies (used in Part C)", "",
            "- PI `R07` on line L2 -> robot RB07; station = ceil(07 / 2) = ST04 (two robots per station).",
            "- MES `B<n>-<ss>` -> `DDN1-BIW-L<n>-ST<ss>`; `SLR-<n>` -> `DDN1-PNT-SL-ST0<n>`; `F1-<ss>` -> `DDN1-ASM-FN1-ST<ss>`.",
            "- Tool `TCnn` -> nutrunner `NRnn` (its controller is `...-NRnn-TC`).",
            "- Drawing `RB-2nn` -> line 2, robot nn; `AHU-01/02/03` -> AHUTC1 / AHUTC2 / AHUPR; zone `Bn` -> OV2-Zn.",
            "- Alarm source: replace `.` `/` with `_`, `S<n>` -> `ST0<n>`, then it is the FL without `DDN1-`.",
            "- Exception list: `L1ST3_RB5` tags -> `DDN1-BIW-L2-ST06-RB12` (relocated Mar-2026).", ""]
    return "\n".join(out)


def main() -> None:
    path = REPORTS / "03_identity_schemes.md"
    path.write_text(to_markdown(), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
