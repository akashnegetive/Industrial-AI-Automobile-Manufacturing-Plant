"""Part C4 - work orders: failure modes (ISO 14224) and equipment mentions with spaCy.

spaCy is used as a rule-based NER: a blank English pipeline plus an EntityRuler.
No statistical model has to be downloaded, so it works offline and every
extraction can be traced back to the rule that produced it.

Entities:
    FAILURE    phrase that describes a failure ("gun water leak", "trip ho raha hai")
               -> entity id = ISO 14224 failure-mode code
    ACTIVITY   phrase that describes routine work, not a failure ("PM", "within tolerance")
    EQUIPMENT  equipment reference ("R7", "DC tool 14", "Sealer robo 3") -> canonical code
               via textnorm (the asset itself is resolved by the Day-5 matcher)

The SAP failure_code column is not used for training or evaluation: it is filled
on only 66 % of corrective WOs and is unrelated to the text (see report).

Run:  python -m ddn.workorders     (writes data/staging/wo_failure_modes.parquet, reports/08_workorders.md)
"""
from __future__ import annotations

import re

import pandas as pd
import spacy

from .config import REPORTS, STAGING
from .load import load
from .textnorm import extract, translate

# ISO 14224 failure-mode codes used by the plant manuals (MAN-*), plus the general ones needed for WO text.
ISO14224 = {
    "ELU": "External leakage - utility medium", "ELP": "External leakage - process medium",
    "VIB": "Vibration", "NOI": "Noise", "STD": "Structural deficiency (wear, breakage, damage)",
    "FTS": "Fail to start on demand", "UST": "Spurious stop", "ERO": "Erratic output",
    "OHE": "Overheating", "LOO": "Low output", "HIO": "High output", "PDE": "Parameter deviation",
    "PLU": "Plugged / choked", "FTC": "Fail to close on demand", "AIR": "Abnormal instrument reading",
    "SER": "Minor in-service problem",
}

# (ISO code, phrases). Order = priority when a text matches several (most specific first).
FAILURE_PHRASES = [
    ("PDE", ["found offset", "shut height", "out of tolerance", "tonnage high", "offset"]),
    ("AIR", ["reading frozen", "sensor faulty", "sensor fault", "not changing", "thermocouple checked", "sensor calibrated"]),
    ("FTC", ["stuck open", "valve stuck"]),
    ("ELU", ["water leak", "cooling water leak", "refrigerant leak"]),
    ("ELP", ["seal leaking", "mechanical seal leaking", "nozzle dripping", "dripping", "oil leak", "leaking"]),
    ("HIO", ["valve hunting", "zone over-temperature"]),          # burner manual: zone over-temp = HIO
    ("OHE", ["overtemp", "over-temperature", "overheating", "high discharge temp", "high temp"]),
    ("ERO", ["hunting", "unstable", "comm fault", "lost guidance", "sluggish", "erratic"]),
    ("LOO", ["temp low", "not heating", "pressure low", "low refrigerant", "not charging", "not coming up",
             "current low", "low output"]),
    ("PLU", ["blocked", "choked", "clogged"]),
    ("FTS", ["not running", "flame failure", "no ignition", "not starting", "spindle not running"]),
    ("UST", ["trip", "tripping", "overload", "fault e-", "reset and restarted"]),
    ("VIB", ["high vibration", "vibration"]),
    ("NOI", ["bearing noise", "noisy", "noise"]),
    ("STD", ["worn", "broken", "damaged", "chipped", "crack", "chain stretch", "belt loose", "coupling rubber"]),
    ("SER", ["tip dress fail", "tip dressing fail", "jam", "cleared", "re-taught", "misaligned"]),
]
ROUTINE_PHRASES = ["pm", "ir test", "within tolerance", "within spec", "check, ok", "check ok", "annual calibration",
                   "service", "profile run", "master check", "descaled", "greasing", "cleaning", "route check",
                   "combustion tuning", "calibration", "shunt check"]


def build_nlp() -> spacy.language.Language:
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER"})
    patterns = []
    for code, phrases in FAILURE_PHRASES:
        patterns += [{"label": "FAILURE", "pattern": p, "id": code} for p in phrases]
    patterns += [{"label": "ACTIVITY", "pattern": p, "id": "ROUTINE"} for p in ROUTINE_PHRASES]
    # equipment references as token patterns: R7, RB07, NR14, SR-03, P-104, AGV 03 ...
    patterns += [{"label": "EQUIPMENT", "pattern": [{"TEXT": {"REGEX": r"^(?:RB?|NR|SR|P|T|AGV|CMP|DRY|CH|CV|FILL|TRB|PRB|UF|HX)-?\d{1,3}[AB]?$"}}]},
                 {"label": "EQUIPMENT", "pattern": [{"LOWER": {"IN": ["rob", "robot", "nutrunner", "agv"]}},
                                                    {"LIKE_NUM": True}]},
                 {"label": "EQUIPMENT", "pattern": [{"LOWER": "dc"}, {"LOWER": "tool"}, {"LIKE_NUM": True}]},
                 {"label": "EQUIPMENT", "pattern": [{"LOWER": "robot"}, {"LOWER": "no"}, {"LIKE_NUM": True}]}]
    ruler.add_patterns(patterns)
    return nlp


PRIORITY = {code: i for i, (code, _) in enumerate(FAILURE_PHRASES)}


def analyse(nlp, wos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    texts = (wos.short_text.fillna("") + ". " + wos.long_text.fillna("")).map(translate)
    for wo, doc in zip(wos.itertuples(), nlp.pipe(texts)):
        fails = [(e.ent_id_, e.text) for e in doc.ents if e.label_ == "FAILURE"]
        routine = [e.text for e in doc.ents if e.label_ == "ACTIVITY"]
        equip = [e.text for e in doc.ents if e.label_ == "EQUIPMENT"]
        fails.sort(key=lambda f: PRIORITY[f[0]])
        # A PM/CAL order only gets a failure mode if it found something ("found offset").
        if fails and (wo.wo_type == "CM" or fails[0][0] in {"PDE", "AIR"}):
            code, phrase, activity = fails[0][0], fails[0][1], "failure"
        elif routine or wo.wo_type in {"PM", "CAL"}:
            code, phrase, activity = None, (routine[0] if routine else wo.wo_type), "routine"
        else:
            code, phrase, activity = None, None, "unclassified"
        rows.append({"wo_number": wo.wo_number, "wo_type": wo.wo_type, "activity": activity,
                     "iso14224": code, "iso14224_name": ISO14224.get(code), "evidence": phrase,
                     "all_failures": ";".join(sorted({c for c, _ in fails})),
                     "equipment_mentions": ";".join(equip), "canonical_tokens": extract(texts[wo.Index]).as_text(),
                     "sap_failure_code": wo.failure_code})
    return pd.DataFrame(rows)


def main() -> None:
    wos = load("maintenance_work_orders.csv")
    res = analyse(build_nlp(), wos)
    links = pd.read_parquet(STAGING / "links_wo_number.parquet")
    res = res.merge(links[["wo_number", "functional_location", "confidence", "band"]], on="wo_number", how="left")
    res.to_parquet(STAGING / "wo_failure_modes.parquet", index=False)

    cm = res[res.wo_type == "CM"]
    cov = cm.iso14224.notna().mean()
    dist = res.iso14224.value_counts()
    sap = pd.crosstab(cm.iso14224.fillna("—"), cm.sap_failure_code.fillna("blank"))
    out = ["# Part C4 – Work orders: failure modes (ISO 14224) and equipment mentions", "",
           "Generated by `python -m ddn.workorders`. spaCy blank English pipeline + EntityRuler (rule-based NER, "
           "no model download). Hinglish is translated first (`textnorm.translate`).", "",
           f"- {len(res):,} work orders: {(res.activity == 'failure').sum():,} failures, "
           f"{(res.activity == 'routine').sum():,} routine (PM/CAL/inspection), "
           f"{(res.activity == 'unclassified').sum():,} unclassified",
           f"- **Corrective (CM) work orders with a failure mode: {cov:.1%}** ({cm.iso14224.notna().sum():,} of {len(cm):,})",
           f"- Work orders linked to an asset by the Day-5 matcher: {res.functional_location.notna().mean():.1%}", "",
           "## Failure modes found", "", "| ISO 14224 | Meaning | Work orders |", "|---|---|---:|"]
    out += [f"| `{c}` | {ISO14224[c]} | {n} |" for c, n in dist.items()]
    out += ["", "## Why the SAP failure_code is not used", "",
            "Each extracted mode (rows) is spread almost evenly over the SAP codes (columns): the field does not "
            "describe the failure. It is also blank on 34 % of CM orders and on every PM/CAL order.", "",
            "| Extracted \\ SAP | " + " | ".join(sap.columns) + " |", "|---|" + "---:|" * len(sap.columns)]
    out += [f"| {i} | " + " | ".join(str(v) for v in row) + " |" for i, row in sap.iterrows()]
    unc = res[res.activity == "unclassified"]
    out += ["", f"## Unclassified ({len(unc)}) – candidates for new phrases", ""]
    out += [f"- {wos.set_index('wo_number').short_text[w]}" for w in unc.wo_number.head(15)]
    ex = res[res.activity == "failure"].merge(wos[["wo_number", "short_text"]], on="wo_number")
    hing = ex[ex.short_text.str.contains(r"\b(?:nahi|raha|hai|kiya)\b", case=False)]
    out += ["", "## Examples", "", "| WO | Text | Failure mode | Evidence | Equipment mentions | Linked asset |",
            "|---|---|---|---|---|---|"]
    for _, r in pd.concat([ex.sample(12, random_state=3), hing.head(4)]).iterrows():
        out.append(f"| {r.wo_number} | {r.short_text} | `{r.iso14224}` | {r.evidence} | {r.equipment_mentions} | "
                   f"`{r.functional_location}` |")
    path = REPORTS / "08_workorders.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"work orders: CM with failure mode {cov:.1%}; modes {dist.to_dict()} -> {path}")


if __name__ == "__main__":
    main()
