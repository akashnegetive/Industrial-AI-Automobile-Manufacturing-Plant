"""Turn messy equipment references into canonical tokens.

Technicians, PLCs and historians all write the same robot differently:
    "R7", "Rob 07", "robot no 7", "RB07", "L2 ST4 robo"
This module maps such text to the tokens used in functional locations:
    lines {L2}, stations {ST04}, equipment {RB07}, components {WG}

The same extractor runs on asset names, tag names/descriptions and work-order
text, so the matcher compares like with like.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Hinglish / shorthand -> English, applied before token extraction (Part C4).
HINGLISH = {
    r"\bsealer robo(?:t)?\s?(\d)\b": r"SR\1",          # must run before robo -> robot
    r"\bnahi chal raha\b": "not running", r"\bchal nahi raha\b": "not running",
    r"\btrip ho raha hai\b": "tripping", r"\bho raha hai\b": "happening",
    r"\baa raha tha\b": "was coming", r"\bkiya\b": "done", r"\bka\b": "of", r"\bbadla\b": "replaced",
    r"\brobo\b": "robot",
}

# Words that name a component (last FL segment) -> FL code.
COMPONENT_WORDS = [
    (r"\bweld gun\b|\bgun\b|\bWG\b", "WG"),
    (r"\btool controller\b|\bcontroller\b|\bTC\b", "TC"),
    (r"\bmain motor\b|\bmotor\b|\bMTR\b", "MTR"),
    (r"\btip dresser\b|\bTD\b", "TD"),
    (r"\bheated dispenser\b|\bdispenser\b|\bDSP\b", "DSP"),
    (r"\bfixture\b|\bFX\b", "FX"),
    (r"\bhumidifier\b|\bHUM\b", "HUM"),
    (r"\bsupply fan\b|\bSF\b", "SF"),
    (r"\bexhaust fan\b|\bEF\b", "EF"),
    (r"\bburner\b|\bBR\b", "BR"),
    (r"\bcirculation fan\b|\bFAN\b", "FAN"),
    (r"\blube pump\b|\bLUB\b", "LUB"),
    (r"\bhydraulic overload\b|\bOLP\b|\bHOL\b", "HOL"),
    (r"\bbell\b|\batomi[sz]er\b", "BELL"),
    (r"\bRFID\b", "RFID"),
    (r"\brig\b", "RIG"),
]

# (pattern, template) - template gets the zero-padded number.
EQUIP_PATTERNS = [
    (r"\b(?:RB|R|Rob\.?|Robot(?: no\.?)?|robot no\.?)\s?-?(\d{1,2})\b", "RB{:02d}"),
    (r"\b(?:NR|Nutrunner|nutrunner|DC tool|DC-?)\s?(\d{1,2})\b", "NR{:02d}"),
    (r"\b(?:SR-?|Sealer robot SR-|Sealer robo |sealer robot )(\d{1,2})\b", "SR{:02d}"),
    (r"\bAGV\s?(\d{1,2})\b", "AGV{:02d}"),
    (r"\bFILL\s?(\d{1,2})\b|\bFill machine (\d{1,2})\b", "FILL{:02d}"),
    (r"\bCMP-?(\d{1,2})\b", "CMP{:02d}"),
    (r"\bDRY-?(\d{1,2})\b", "DRY{:02d}"),
    (r"\bCH-(\d{1,2})\b|\bCH(\d{2})\b", "CH{:02d}"),     # chiller CH-01 / CH01 (CH1 alone is the chassis line)
    (r"\bCT-?(\d{1,2})\b", "CT{:02d}"),
    (r"\bCV\s?(\d{1,2})\b", "CV{:02d}"),
    (r"\b(?:PR|Press)\s?(\d)\b", "PR{}"),
    (r"\bTRB\s?(\d{1,2})\b|\btopcoat \d robot (\d{1,2})\b", "TRB{:02d}"),
    (r"\bPRB\s?(\d{1,2})\b|\bprimer robot (\d{1,2})\b", "PRB{:02d}"),
    (r"\b(?:zone|Z)\s?(\d)\b", "Z{}"),
]
SIMPLE_CODES = [  # already canonical apart from a dash: P-104 -> P104, T-301 -> T301
    r"\bP-?(\d{3}[AB]?)\b", r"\bT-?(\d{3})\b", r"\bHX-?(\d{3})\b", r"\bUF-?(\d{3})\b", r"\bRECT-?(\d{3})\b",
]
LINE_PATTERNS = [
    (r"\bL\s?([123])\b", "L{}"), (r"\bPL\s?([12])\b", "PL{}"), (r"\b(TR[12]|CH1|FN1|EOL)\b", "{}"),
    (r"\b(?:Oven|oven|OV|Ovn|OVN)\s?0?([12])\b", "OV{}"), (r"\b(?:EDO|E-coat oven|EDOven)\b", "EDO"),
    (r"\bTC([12])\b|\bTopcoat ([12])\b|\bbooth ([AB])\b", "TC{}"),
    (r"\b(PT|ED|SL|PR)\b(?!\s?\d)", "{}"),
]
STATION_PATTERNS = [r"\bST\s?0?(\d{1,2})\b", r"\bStation\s?0?(\d{1,2})\b", r"\bS(\d)\b"]


@dataclass
class Tokens:
    lines: set[str] = field(default_factory=set)
    stations: set[str] = field(default_factory=set)
    equip: set[str] = field(default_factory=set)
    comps: set[str] = field(default_factory=set)

    def as_text(self) -> str:
        return " ".join(sorted(self.lines | self.stations | self.equip | self.comps))


def translate(text: str) -> str:
    for pat, rep in HINGLISH.items():
        text = re.sub(pat, rep, text, flags=re.I)
    return text


def extract(text: str) -> Tokens:
    """Canonical tokens from free text, an asset name or a split tag name."""
    t = translate(text or "")
    tok = Tokens()
    for pat, tpl in EQUIP_PATTERNS:
        for m in re.finditer(pat, t, flags=re.I):
            num = next(g for g in m.groups() if g)
            tok.equip.add(tpl.format(int(num)) if "{:02d}" in tpl else tpl.format(num))
    for pat in SIMPLE_CODES:
        for m in re.finditer(pat, t, flags=re.I):
            prefix = re.match(r"\\b([A-Z]+)", pat).group(1)
            tok.equip.add(prefix + m.group(1).upper())
    # ISA-5.1 instrument tags name the loop, and the loop number is the vessel's: TT-301 is on tank T-301
    for m in re.finditer(r"\b(?:TT|TE|TIC|CT|LT|AT)-?(\d{3})\b", t):
        tok.equip.add("T" + m.group(1))
    for m in re.finditer(r"\bAHU[- ]?(TC[12]|PR)\b", t, flags=re.I):
        tok.equip.add("AHU" + m.group(1).upper())
    for pat, tpl in LINE_PATTERNS:
        for m in re.finditer(pat, t):
            g = next((x for x in m.groups() if x), None) if m.groups() else None
            val = tpl.format(g) if g else tpl
            tok.lines.add({"TCA": "TC1", "TCB": "TC2"}.get(val, val))
    for pat in STATION_PATTERNS:
        for m in re.finditer(pat, t):
            tok.stations.add(f"ST{int(m.group(1)):02d}")
    for pat, code in COMPONENT_WORDS:
        if re.search(pat, t, flags=re.I):
            tok.comps.add(code)
    return tok


def split_name(name: str) -> str:
    """Tag name -> space-separated words, so 'DDN1_BIW_L2_R07_WELDCUR.PV' -> 'DDN1 BIW L2 R07 WELDCUR PV'."""
    words = re.sub(r"[_.\-]+", " ", name)
    # glued codes: Z3FAN -> Z3 FAN, ST03FX -> ST03 FX, SR03DSP -> SR03 DSP, PR1HOL -> PR1 HOL
    return re.sub(r"(\d)([A-Z]{2,})", r"\1 \2", words)
