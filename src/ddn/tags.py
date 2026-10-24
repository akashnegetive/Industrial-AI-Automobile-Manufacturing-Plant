"""Part C1 - ingest and normalise: parse tag names and build typed staging tables.

Each historian tag is split into the parts the matcher needs:

    DDN1_BIW_L2_R07_WELDCUR.PV   (PI)     -> shop BIW, line L2,  equip RB07,    signal WELDCUR
    PaintShop-Ovn02-Z3-Temp      (WinCC)  -> shop PNT, line OV2, equip Z3,      signal Temp
    PRS.PL1.PR1HOL.CUR           (S7)     -> shop PRS, line PL1, equip PR1HOL,  signal CUR
    FA_FN1_NR14_TQLAST           (MES)    -> shop ASM, line FN1, equip NR14,    signal TQLAST

Only *documented* naming variants are normalised here (area spellings,
R07 -> RB07). Zero padding (AGV7 vs AGV07) is ambiguous - SAP itself has both
AGV07 and P1 - so the matcher tries both forms instead. Genuine typos are left alone: the rules matcher should
fail on them, and Day 5's fuzzy/ML matcher must recover them.

Run:  python -m ddn.tags     (writes data/staging/*.parquet)
"""
from __future__ import annotations

import re
import shutil

import pandas as pd
from pydantic import BaseModel

from .config import STAGING
from .load import load

# WinCC area spellings seen in the data -> canonical line code used in SAP.
AREA_ALIASES = {
    "OVEN1": "OV1", "OVN1": "OV1", "OVN01": "OV1", "OVEN01": "OV1",
    "OVEN2": "OV2", "OVN2": "OV2", "OVN02": "OV2", "OVEN02": "OV2",
    "EDOVEN": "EDO", "EDO": "EDO", "ECOATOVEN": "EDO",
    "AHU": "AHU", "AIRHANDLING": "AHU",
}

# Signal token -> ISA-5.1 measured-variable letter + function (T = transmitter).
# Only signals that are real measurements get a code; status/fault/counters do not.
ISA51 = {
    "TEMP": "TT", "NOZTEMP": "TT", "HTRTEMP": "TT", "TOUT": "TT", "SUPT": "TT", "RETT": "TT",
    "A1TEMP": "TT", "A2TEMP": "TT", "A3TEMP": "TT", "A4TEMP": "TT", "A5TEMP": "TT", "A6TEMP": "TT",
    "PRESS": "PT", "LUBEP": "PT", "DPF": "PDT",
    "FLOW": "FT", "LVL": "LT", "COND": "CT", "PH": "AT", "RH": "MT", "VIB": "VT",
    "CUR": "IT", "WELDCUR": "IT", "VOLT": "ET", "HV": "ET",
    "SPD": "ST", "BELLSPD": "ST", "SPM": "ST", "TON": "WT", "GUNFORCE": "WT",
}

# Temperatures configured in deg F (WinCC) are converted so the whole plant is in deg C.
UNIT_CANONICAL = {"degF": "degC"}


class TagRecord(BaseModel):
    """One historian tag after parsing. pydantic rejects wrong types at load time."""
    tag_name: str
    source_system: str
    description: str | None
    unit: str | None
    unit_canonical: str | None
    shop: str | None
    line: str | None
    equip: str | None
    signal: str | None
    isa51_code: str | None
    legacy_name: bool = False     # e.g. relocated robot still using its old controller name
    parsed: bool                  # False = name breaks its documented convention


def _pad(token: str) -> str:
    """AGV7 -> AGV07, RB5 -> RB05 (letters followed by a single digit)."""
    return re.sub(r"^([A-Z]+)(\d)$", r"\g<1>0\2", token)


def parse_tag(name: str, source: str) -> dict:
    """Split a tag into shop / line / equip / signal. Unparseable parts stay None."""
    out = dict(shop=None, line=None, equip=None, signal=None, legacy_name=False, parsed=False)

    if source == "PI Historian":
        m = re.match(r"^DDN1_([A-Z]+)_([A-Z0-9]+)_([A-Z0-9]+)_([A-Z0-9]+)\.PV$", name)
        if not m:
            return out
        shop, line, equip, signal = m.groups()
        legacy = re.match(r"^L(\d)ST(\d)$", line)          # relocated robot: L1ST3_RB5
        if legacy:
            out.update(legacy_name=True)
            line = f"L{legacy.group(1)}"
            equip = f"ST0{legacy.group(2)}-{_pad(equip)}"   # station is explicit in the old name
        elif shop == "BIW" and re.match(r"^R\d{2}$", equip):
            equip = "RB" + equip[1:]                        # PI uses R07, SAP uses RB07
        out.update(shop=shop, line=line, equip=equip, signal=signal, parsed=True)

    elif source == "WinCC SCADA":
        m = re.match(r"^PaintShop-([A-Za-z0-9]+)-([A-Za-z0-9]+)-([A-Za-z0-9]+)$", name)
        if not m:
            return out
        area, equip, signal = m.groups()
        line = AREA_ALIASES.get(area.upper())
        out.update(shop="PNT", line=line, equip=equip.upper(), signal=signal.upper(), parsed=line is not None)

    elif source == "S7 legacy OPC":
        m = re.match(r"^([A-Z]+)\.([A-Z0-9]+)\.([A-Z0-9]+)\.([A-Z0-9]+)$", name)
        if not m:
            return out
        shop, line, equip, signal = m.groups()
        out.update(shop=shop, line=line, equip=equip, signal=signal, parsed=True)

    elif source == "MES":
        m = re.match(r"^FA_([A-Z0-9]+)_([A-Z0-9]+)_([A-Z0-9]+)$", name)
        if not m:
            return out
        line, equip, signal = m.groups()
        out.update(shop="ASM", line=line, equip=equip, signal=signal, parsed=True)
    return out


def stage_tags() -> pd.DataFrame:
    t = load("historian_tag_list.csv")
    records = []
    for r in t.itertuples():
        p = parse_tag(r.tag_name, r.source_system)
        unit = None if pd.isna(r.engineering_unit) else r.engineering_unit
        records.append(TagRecord(
            tag_name=r.tag_name, source_system=r.source_system,
            description=None if pd.isna(r.description) else r.description,
            unit=unit, unit_canonical=UNIT_CANONICAL.get(unit, unit),
            isa51_code=ISA51.get(p["signal"]) if p["signal"] else None, **p))
    return pd.DataFrame([rec.model_dump() for rec in records])


def stage_assets() -> pd.DataFrame:
    """Asset master with levels split out and missing parents repaired from the path."""
    a = load("assets_cmms_export.csv")
    fl = set(a.functional_location)

    def implied_parent(f: str) -> str | None:
        # walk up the path until an existing FL is found (handles dies with '-' in their id)
        parts = f.split("-")
        for i in range(len(parts) - 1, 0, -1):
            cand = "-".join(parts[:i])
            if cand in fl:
                return cand
        return None

    a["parent_repaired"] = a.parent_functional_location.isna() & (a.asset_type != "Site")
    a["parent_fl"] = a.parent_functional_location.fillna(a.functional_location.map(implied_parent))
    segs = a.functional_location.str.split("-")
    a["shop"] = segs.str[1]
    a["line"] = segs.str[2]
    a["below_line"] = segs.str[3:].str.join("-")     # e.g. ST04-RB07, T106-P106, Z3-FAN
    return a


def stage_timeseries(tags: pd.DataFrame) -> pd.DataFrame:
    """Long-format values with deg F converted to deg C, stored partitioned by tag."""
    ts = load("timeseries_1min.csv.gz")
    degf = set(tags.loc[tags.unit == "degF", "tag_name"])
    is_f = ts.tag_name.isin(degf)
    ts["value_raw"] = ts.value
    ts.loc[is_f, "value"] = ((ts.loc[is_f, "value"] - 32) * 5 / 9).round(2)
    ts["unit"] = ts.tag_name.map(tags.set_index("tag_name").unit_canonical)
    return ts


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    tags = stage_tags()
    tags.to_parquet(STAGING / "tags.parquet", index=False)
    assets = stage_assets()
    assets.to_parquet(STAGING / "assets.parquet", index=False)
    ts = stage_timeseries(tags)
    # Partitioned writes add files to an existing folder, so clear it to avoid duplicate rows.
    shutil.rmtree(STAGING / "timeseries", ignore_errors=True)
    ts.to_parquet(STAGING / "timeseries", partition_cols=["tag_name"], index=False)
    print(f"tags: {len(tags)} ({(~tags.parsed).sum()} break their naming convention, "
          f"{tags.legacy_name.sum()} legacy names)")
    print(f"assets: {len(assets)} ({assets.parent_repaired.sum()} parents repaired)")
    print(f"timeseries: {len(ts):,} values, {ts.tag_name.nunique()} tags -> {STAGING / 'timeseries'}")


if __name__ == "__main__":
    main()
