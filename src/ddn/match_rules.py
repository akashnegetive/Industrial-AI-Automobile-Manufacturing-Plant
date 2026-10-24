"""Part C - rules-only tag matcher (the baseline the ML matcher must beat).

Idea: build a lookup index from the asset master, keyed by (shop, line, equipment
key), then look up the parsed tag. No fuzzy logic, no training data.

Index keys are every *suffix* of the FL below the line, with '-' removed:
    DDN1-BIW-L2-ST04-RB07       -> ST04RB07, RB07
    DDN1-PNT-PT-T106-P106       -> T106P106, P106
    DDN1-PNT-OV2-Z3-FAN         -> Z3FAN, FAN
A key that points at more than one asset in the same line (e.g. FAN, FX) is
dropped, so a lookup can never be ambiguous.

Rules are applied in order; the first that fires wins and sets the confidence:
    1. relocation  - legacy controller name listed in an asset description  (0.95)
    2. exact       - tag parsed with the documented convention               (0.99)
    3. alias       - same, but a known spelling variant was normalised       (0.97)
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .tags import _pad

STRUCTURAL = {"Site", "Shop", "Area", "Line", "Station"}


@dataclass
class Match:
    tag_name: str
    functional_location: str | None
    method: str            # relocation | exact | alias | none
    confidence: float
    reason: str


def build_index(assets: pd.DataFrame) -> dict[tuple[str, str, str], str]:
    hits: dict[tuple, set] = defaultdict(set)
    for r in assets[~assets.asset_type.isin(STRUCTURAL)].itertuples():
        segs = [s for s in r.below_line.split("-") if s] if r.below_line else []
        keys = {"".join(segs[i:]) for i in range(len(segs))} if segs else {r.line}  # UTL-CMP02 has no sub-path
        for k in keys:
            hits[(r.shop, r.line, k)].add(r.functional_location)
    return {k: next(iter(v)) for k, v in hits.items() if len(v) == 1}


def build_relocations(assets: pd.DataFrame) -> dict[tuple[str, str, str], str]:
    """Read 'Relocated from L1 ST03 (ex R05)' in descriptions -> legacy key -> current FL."""
    out = {}
    pat = re.compile(r"Relocated from L(\d)\s*ST(\d+)\s*\(ex R(\d+)\)", re.I)
    for r in assets.dropna(subset=["description"]).itertuples():
        m = pat.search(r.description)
        if m:
            line, st, rb = m.groups()
            out[(r.shop, f"L{line}", f"ST{int(st):02d}-RB{int(rb):02d}")] = r.functional_location
    return out


class RulesMatcher:
    def __init__(self, assets: pd.DataFrame):
        self.index = build_index(assets)
        self.relocations = build_relocations(assets)

    def match(self, tag: pd.Series) -> Match:
        name = tag.tag_name
        if not tag.parsed or tag.line is None:
            return Match(name, None, "none", 0.0, "name breaks its naming convention")
        key = (tag.shop, tag.line, tag.equip)
        if tag.legacy_name:
            fl = self.relocations.get(key)
            if fl:
                return Match(name, fl, "relocation", 0.95, f"legacy name {tag.line}/{tag.equip} relocated")
            return Match(name, None, "none", 0.0, "legacy name with no relocation record")
        equip = tag.equip.replace("-", "")
        # Try the token as written, then zero-padded (AGV7 -> AGV07); SAP uses both P1 and AGV07.
        fl = self.index.get((tag.shop, tag.line, equip)) or self.index.get((tag.shop, tag.line, _pad(equip)))
        if fl is None:
            return Match(name, None, "none", 0.0, f"no asset for key {tag.shop}/{tag.line}/{tag.equip}")
        variant = tag.source_system == "WinCC SCADA" and tag.tag_name.split("-")[1] not in {"AHU", "EDO"} \
            and not re.fullmatch(r"OV\d", tag.tag_name.split("-")[1])
        if variant:
            return Match(name, fl, "alias", 0.97, f"area '{tag.tag_name.split('-')[1]}' normalised to {tag.line}")
        return Match(name, fl, "exact", 0.99, "documented convention")

    def match_all(self, tags: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([vars(self.match(r)) for _, r in tags.iterrows()])


class WorkOrderRulesMatcher:
    """Rules-only work-order matcher: uses only the structured fields, never the free text.

    Order = most reliable first:
        1. fl_text  - functional_location_text is an FL fragment ('BIW-L2-ST02-RB04-WG')   (0.97)
        2. name     - functional_location_text equals a unique asset name                  (0.90)
        3. eq_no    - SAP equipment number (known to be wrong in ~4 % of labelled WOs)      (0.85)
    """

    def __init__(self, assets: pd.DataFrame):
        self.fls = set(assets.functional_location)
        names = assets.groupby(assets.name.str.lower()).functional_location.agg(list)
        self.unique_names = {n: fls[0] for n, fls in names.items() if len(fls) == 1}
        eq = assets.dropna(subset=["cmms_equipment_no"])
        self.eq = dict(zip(eq.cmms_equipment_no, eq.functional_location))

    def match(self, wo: pd.Series) -> Match:
        text = wo.functional_location_text if pd.notna(wo.functional_location_text) else ""
        candidate = "DDN1-" + text.strip().upper()
        if text and candidate in self.fls:
            return Match(wo.wo_number, candidate, "fl_text", 0.97, f"FL text '{text}'")
        if text and text.strip().lower() in self.unique_names:
            return Match(wo.wo_number, self.unique_names[text.strip().lower()], "name", 0.90, f"asset name '{text}'")
        if pd.notna(wo.equipment_no) and wo.equipment_no in self.eq:
            return Match(wo.wo_number, self.eq[wo.equipment_no], "eq_no", 0.85, f"equipment no {wo.equipment_no}")
        return Match(wo.wo_number, None, "none", 0.0, "no structured identifier" if not text
                     else f"FL text '{text}' is ambiguous or unknown")

    def match_all(self, wos: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame([vars(self.match(r)) for _, r in wos.iterrows()])
        return out.rename(columns={"tag_name": "wo_number"})
