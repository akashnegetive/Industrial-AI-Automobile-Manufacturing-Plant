"""Part C5 - documents: extract equipment labels from drawings and manuals.

Drawings
    1. Text from the PDF text layer (PyMuPDF). If a page has no text layer it is
       a scan: render it and run Tesseract OCR (several settings, merged).
    2. The drawing number gives the context: DWG-BIW-L2-001 -> shop BIW, line L2.
    3. LABEL_RULES turn local labels into asset keys, e.g. on a Line-2 drawing
       RB-207 -> RB07, TD-2.04 -> ST04TD, on the oven-B drawing BNR-B3 -> Z3BR.
    4. Keys resolve through the same asset index as the tag matcher, and
       instrument labels (TT-301, TE-423, MT-02) resolve to historian tags.
    5. Every hit becomes a `mentionedIn` link with page, label, method, confidence:
         text layer 0.95 | OCR exact 0.85 | OCR after correction 0.70 (-> review)
Manuals
    Linked to equipment by manufacturer model (OR-210 -> every OR-210 robot) and
    mined for alarm-code and failure-mode tables used by work orders and alarms.

Run:  python -m ddn.documents     (writes data/staging/doc_*.parquet, reports/07_documents.md)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pymupdf

from .config import REPORTS, ROOT, STAGING
from .match_rules import build_index

DOCS = ROOT / "docs" / "source_pack" / "documents"
CONF_TEXT, CONF_OCR, CONF_OCR_FIXED = 0.95, 0.85, 0.70

# Drawing number -> (shop, line) context. Oven B is OV2, booth B is TC2 (plant overview).
CONTEXT = {
    "DWG-BIW-L2-001": ("BIW", "L2"), "DWG-PNT-SL-201": ("PNT", "SL"), "DWG-PNT-AHU-301": ("PNT", "AHU"),
    "DWG-PNT-OV-402": ("PNT", "OV2"), "DWG-PNT-ED-101": ("PNT", "ED"), "DWG-ASM-FN1-501": ("ASM", "FN1"),
    "DWG-PRS-PL1-601": ("PRS", "PL1"),
}
AHU_NO = {"01": "AHUTC1", "02": "AHUTC2", "03": "AHUPR"}     # AHU-02 = AHU for booth B (TC2)


def _sr(cell: str, side: str) -> str:
    """Sealer TE 2<cell><side>: cell 1-3, side 1 = odd robot, 2 = even robot."""
    return f"SR{2 * (int(cell) - 1) + int(side):02d}"


# (regex on normalised text, function(match, line) -> ("asset", key) or ("tag", (equip, signal)))
LABEL_RULES = [
    (r"\bRB-\d(\d{2})\b", lambda m, ln: ("asset", f"RB{m[1]}")),
    (r"\bWG-\d(\d{2})\b", lambda m, ln: ("asset", f"RB{m[1]}WG")),
    (r"\bTD-\d\.(\d{2})\b", lambda m, ln: ("asset", f"ST{m[1]}TD")),
    (r"\bFX-\d\.(\d{2})\b", lambda m, ln: ("asset", f"ST{m[1]}FX")),
    (r"\bSR-(\d{2})\b", lambda m, ln: ("asset", f"SR{m[1]}")),
    (r"\bHD-(\d{2})\b", lambda m, ln: ("asset", f"SR{m[1]}DSP")),
    (r"\bTE\s?2([123])([12])\b", lambda m, ln: ("tag", (_sr(m[1], m[2]), "NOZTEMP"))),
    (r"\bAHU-(0[123])\b", lambda m, ln: ("asset", AHU_NO[m[1]])),
    (r"\b(HUM|SF|EF)-(0[123])\b", lambda m, ln: ("asset", AHU_NO[m[2]] + m[1])),
    (r"\bMT\s?(0[123])\b", lambda m, ln: ("tag", (AHU_NO[m[1]], "RH"))),
    (r"\bVT\s?(0[123])\b", lambda m, ln: ("tag", (AHU_NO[m[1]] + "SF", "VIB"))),
    (r"\bBNR-B([1-4])\b", lambda m, ln: ("asset", f"Z{m[1]}BR")),
    (r"\bCF-B([1-4])\b", lambda m, ln: ("asset", f"Z{m[1]}FAN")),
    (r"\bZONE B([1-4])\b", lambda m, ln: ("asset", f"Z{m[1]}")),
    (r"\bTE\s?42([1-4])\b", lambda m, ln: ("tag", (f"Z{m[1]}", "TEMP"))),
    (r"\bT-(301)\b", lambda m, ln: ("asset", "T301")),
    (r"\bP-(301[AB])\b", lambda m, ln: ("asset", f"P{m[1]}")),
    (r"\bE-301\b", lambda m, ln: ("asset", "HX301")),
    (r"\bRECT-301\b", lambda m, ln: ("asset", "RECT301")),
    (r"\bUF-301\b", lambda m, ln: ("asset", "UF301")),
    (r"\b(TT|TIC)\s?301\b", lambda m, ln: ("tag", ("T301", "TEMP"))),
    (r"\bCT\s?301\b", lambda m, ln: ("tag", ("T301", "COND"))),
    (r"\bLT\s?301\b", lambda m, ln: ("tag", ("T301", "LVL"))),
    (r"\bDC-(\d{2})\b", lambda m, ln: ("asset", f"NR{m[1]}")),
    (r"\bctrl TC(\d{2})\b", lambda m, ln: ("asset", f"NR{m[1]}TC")),
    (r"\bFM-(\d{2})\b", lambda m, ln: ("asset", f"FILL{m[1]}")),
    (r"\bP1-([1-5])\b", lambda m, ln: ("asset", f"PR{m[1]}")),
    (r"\bOLP-1\.([1-5])\b", lambda m, ln: ("asset", f"PR{m[1]}HOL")),
    (r"\bLUB-1\.([1-5])\b", lambda m, ln: ("asset", f"PR{m[1]}LUB")),
    (r"\bDST-1\b", lambda m, ln: ("asset", "DST")),
    (r"\bTRF-1\b", lambda m, ln: ("asset", "TRF")),
    (r"\bCV-(\d)\b", lambda m, ln: ("asset", "CV01")),
]
DIE_RULE = re.compile(r"\bD-[A-Z]{2,6}(?:-[A-Z]{1,2})?-\d{2}\b")

# OCR confusions on small fonts, each applied only inside a known label shape.
OCR_FIXES = [
    (r"\b[O0Q]L[PF]-?[1T7I]\.?\s?([1-5])\b", r"OLP-1.\1"),
    (r"\bLU[BSG8]-?[1T7I]\.?\s?([1-5])\b", r"LUB-1.\1"),
    (r"\bP[1TI]-([1-5])\b", r"P1-\1"),
    (r"\bD-BS[O0]-\.?[LI]?H-03\b", "D-BSO-LH-03"),
]


@dataclass
class Mention:
    doc_id: str
    page: int
    label: str
    target_kind: str          # asset | timeseries | unresolved
    target: str | None
    method: str               # text | ocr | ocr_corrected
    confidence: float


# ------------------------------------------------------------------ text
def page_texts(path: Path) -> list[tuple[int, str, str]]:
    """(page number, text, method) for each page; OCR when there is no text layer."""
    out = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                out.append((i, text, "text"))
                continue
            try:
                out.append((i, ocr_page(page), "ocr"))
            except Exception as exc:          # Tesseract not installed (e.g. a fresh Windows laptop)
                print(f"  OCR skipped for {path.name} p.{i}: {type(exc).__name__} - install Tesseract to read scans")
                out.append((i, "", "ocr_unavailable"))
    return out


def _find_tesseract() -> None:
    """Use Tesseract from PATH, or from the default Windows install folder if PATH was not set."""
    import os
    import shutil

    import pytesseract
    if shutil.which("tesseract"):
        return
    for exe in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(exe):
            pytesseract.pytesseract.tesseract_cmd = exe
            return


def ocr_page(page) -> str:
    """Several Tesseract passes merged: block mode finds big labels, sparse mode finds small ones."""
    import pytesseract
    from PIL import Image, ImageOps
    _find_tesseract()
    texts = []
    for dpi in (300, 400):
        pix = page.get_pixmap(dpi=dpi)
        img = ImageOps.grayscale(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        img = img.point(lambda v: 0 if v < 160 else 255)      # binarise the grey scan background away
        for psm in (6, 11):
            texts.append(pytesseract.image_to_string(img, config=f"--psm {psm}"))
    return "\n".join(texts)


def normalise(text: str) -> str:
    t = text.replace(",", ".").replace("—", "-").replace("–", "-")
    t = re.sub(r"(?<=[A-Z])\s*-\s*(?=\d)", "-", t)
    return re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", t)


# --------------------------------------------------------------- resolve
class Resolver:
    def __init__(self, assets: pd.DataFrame, tags: pd.DataFrame):
        self.index = build_index(assets)
        self.fls = set(assets.functional_location)
        self.tags = tags[tags.parsed]

    def asset(self, shop: str, line: str, key: str) -> str | None:
        return self.index.get((shop, line, key))

    def tag(self, shop: str, line: str, equip: str, signal: str) -> str | None:
        t = self.tags[(self.tags.shop == shop) & (self.tags.line == line) & (self.tags.equip == equip)
                      & (self.tags.signal.str.upper() == signal)]
        return t.tag_name.min() if len(t) else None      # min(): deterministic if several spellings exist


def drawing_mentions(path: Path, res: Resolver) -> list[Mention]:
    doc_id = re.match(r"(DWG-[A-Z]+-[A-Z0-9]+-\d+)", path.stem)[1]
    shop, line = CONTEXT[doc_id]
    out, seen = [], set()
    for page, raw, method in page_texts(path):
        text = normalise(raw)
        variants = [(text, method, CONF_TEXT if method == "text" else CONF_OCR)]
        if method == "ocr":
            fixed = text
            for pat, rep in OCR_FIXES:
                fixed = re.sub(pat, rep, fixed)
            variants.append((fixed, "ocr_corrected", CONF_OCR_FIXED))
        for txt, meth, conf in variants:
            hits = [(m[0], fn(m, line)) for pat, fn in LABEL_RULES for m in re.finditer(pat, txt)]
            hits += [(m[0], ("die", m[0])) for m in DIE_RULE.finditer(txt)]
            for label, (kind, key) in hits:
                if (page, label) in seen:
                    continue                                   # keep the most confident reading only
                seen.add((page, label))
                if kind == "asset":
                    target = res.asset(shop, line, key)
                elif kind == "die":
                    target = f"DDN1-PRS-DIES-{key}" if f"DDN1-PRS-DIES-{key}" in res.fls else None
                    kind = "asset"
                else:
                    target = res.tag(shop, line, *key)
                    kind = "timeseries"
                out.append(Mention(doc_id, page, label, kind if target else "unresolved", target, meth, conf))
    return out


# ---------------------------------------------------------------- manuals
def manual_tables(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Alarm codes and ISO 14224-style failure modes from a manual excerpt."""
    with pymupdf.open(path) as doc:
        text = "\n".join(p.get_text() for p in doc)
    flat = re.sub(r"\s+", " ", text)
    alarms = []
    sec = re.search(r"Alarm codes Code Message Typical causes (.*?)(?: Failure modes| Troubleshooting|$)", flat)
    if sec:
        parts = re.split(r"\b([A-Z]{1,4}-\d{2,3})\b", sec[1])
        for code, body in zip(parts[1::2], parts[2::2]):
            alarms.append({"code": code, "text": body.strip()})
    modes = []
    sec = re.search(r"Failure modes \(ISO 14224 style codes\) Code Failure mode Effect in the plant (.*?)(?: Troubleshooting|$)", flat)
    if sec:
        parts = re.split(r"\b([A-Z]{3})\b", sec[1])
        for code, body in zip(parts[1::2], parts[2::2]):
            modes.append({"code": code, "text": body.strip()})
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = next((ln for ln in lines if not ln.startswith(("Plant DDN-01", "Page "))), lines[0])
    return pd.DataFrame(alarms), pd.DataFrame(modes), title


# Which models each manual covers, read from the manual titles. "variant" = same family,
# different model (the manual probably applies, but an engineer should confirm -> review band).
MANUAL_MODELS = {
    "MAN-ORN-OR210": {"exact": ["OR-210 Spot"], "variant": ["OR-210L Spot"]},
    "MAN-TQX-DC500": {"exact": ["TorqX DC-500", "TorqX TC-2"], "variant": ["TorqX DC-250"]},
    "MAN-SFL-SFH2": {"exact": ["SF-Heated-2"], "variant": []},
    "MAN-TLN-GM2": {"exact": ["TL-GasModu 2MW"], "variant": []},
    "MAN-BPW-1200": {"exact": ["BPW-1200T", "BPW-800T"], "variant": []},   # title: BPW-1200T / 800T
    "MAN-AMX-AHU60K": {"exact": ["AM-AHU-60k"], "variant": []},
}


def manual_links(doc_id: str, assets: pd.DataFrame) -> list[Mention]:
    """Manual -> every asset of a model it covers. Exact model 0.90, family variant 0.75."""
    spec = MANUAL_MODELS.get(doc_id, {"exact": [], "variant": []})
    out = []
    for r in assets.dropna(subset=["model"]).itertuples():
        if r.model in spec["exact"]:
            out.append(Mention(doc_id, 1, r.model, "asset", r.functional_location, "model", 0.90))
        elif r.model in spec["variant"]:
            out.append(Mention(doc_id, 1, r.model, "asset", r.functional_location, "model_variant", 0.75))
    return out


def main() -> None:
    assets = pd.read_parquet(STAGING / "assets.parquet")
    tags = pd.read_parquet(STAGING / "tags.parquet")
    res = Resolver(assets, tags)

    mentions = []
    for p in sorted((DOCS / "drawings").glob("*.pdf")):
        mentions += drawing_mentions(p, res)
    alarm_tables, mode_tables, titles = [], [], {}
    for p in sorted((DOCS / "manuals").glob("*.pdf")):
        doc_id = "-".join(p.stem.split("_")[0].split("-")[:3])
        mentions += manual_links(doc_id, assets)
        al, fm, title = manual_tables(p)
        titles[doc_id] = title
        alarm_tables.append(al.assign(manual=doc_id))
        mode_tables.append(fm.assign(manual=doc_id))
    m = pd.DataFrame([vars(x) for x in mentions])
    alarm_codes = pd.concat(alarm_tables, ignore_index=True)
    failure_modes = pd.concat(mode_tables, ignore_index=True)
    m.to_parquet(STAGING / "doc_mentions.parquet", index=False)
    alarm_codes.to_parquet(STAGING / "doc_alarm_codes.parquet", index=False)
    failure_modes.to_parquet(STAGING / "doc_failure_modes.parquet", index=False)

    dr = m[m.doc_id.str.startswith("DWG")]
    summary = dr.groupby(["doc_id", "method"]).agg(labels=("label", "size"),
                                                   resolved=("target", lambda s: s.notna().sum())).reset_index()
    out = ["# Part C5 – Document contextualization", "",
           "Generated by `python -m ddn.documents`. Drawings: PyMuPDF text layer, or Tesseract OCR when the page "
           "is a scan. Labels are mapped with the drawing's context (shop/line from the drawing number).", "",
           "Confidence: text layer 0.95 · OCR exact 0.85 · OCR after correction 0.70 (goes to review) · "
           "manual by exact model 0.90 · model variant 0.75.", "",
           "## Drawings", "", "| Drawing | Method | Labels found | Resolved to asset/tag |", "|---|---|---:|---:|"]
    out += [f"| {r.doc_id} | {r.method} | {r.labels} | {r.resolved} |" for r in summary.itertuples()]
    ocr = dr[dr.method.str.startswith("ocr")]
    unres = dr[dr.target.isna()]
    out += ["", f"**{len(dr)} drawing labels, {dr.target.notna().sum()} resolved, {len(unres)} unresolved.**", ""]
    if len(unres):
        out += ["Unresolved labels (no matching asset or tag in the master data):", ""]
        out += [f"- `{r.label}` on {r.doc_id} p.{r.page} ({r.method})" for r in unres.itertuples()]
    out += ["", "### Scanned drawing (OCR)", "",
            "Checked by eye against the scan: it carries 17 labels (DST-1, TRF-1, P1-1..5, OLP-1.1..5, LUB-1.1..5) plus "
            f"the die D-BSO-LH-03. OCR recovered **{ocr.label.nunique()}** of these 18. Missing labels are not guessed: "
            "they are listed as a data-quality item for a person to add.", "",
            "| Label | Method | Confidence | Target |", "|---|---|---:|---|"]
    out += [f"| `{r.label}` | {r.method} | {r.confidence} | `{r.target}` |" for r in ocr.sort_values("label").itertuples()]
    out += ["", "### Sample of resolved labels", "", "| Drawing | Page | Label | Kind | Target |", "|---|---:|---|---|---|"]
    sample = dr[dr.target.notna() & (dr.method == "text")].groupby("doc_id").head(4)
    out += [f"| {r.doc_id} | {r.page} | `{r.label}` | {r.target_kind} | `{r.target}` |" for r in sample.itertuples()]
    man = m[m.method.isin(["model", "model_variant"])]
    out += ["", "## Manuals", "", "| Manual | Title | Linked assets (exact model / variant) | Alarm codes | Failure modes |",
            "|---|---|---|---:|---:|"]
    for doc_id, title in titles.items():
        g = man[man.doc_id == doc_id]
        out.append(f"| {doc_id} | {title} | {(g.method == 'model').sum()} / {(g.method == 'model_variant').sum()} | "
                   f"{(alarm_codes.manual == doc_id).sum()} | {(failure_modes.manual == doc_id).sum()} |")
    out += ["", "### Alarm codes extracted (used to explain alarms and work orders)", "",
            "| Code | Manual | Message and typical causes |", "|---|---|---|"]
    out += [f"| `{r.code}` | {r.manual} | {r.text[:110]} |" for r in alarm_codes.itertuples()]
    out += ["", "### Failure modes extracted", "", "| Code | Manual | Meaning / effect |", "|---|---|---|"]
    out += [f"| `{r.code}` | {r.manual} | {r.text[:110]} |" for r in failure_modes.itertuples()]
    path = REPORTS / "07_documents.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    ocr_state = "OCR used" if (dr.method.str.startswith("ocr_c") | (dr.method == "ocr")).any() else "OCR NOT used"
    print(f"drawings: {len(dr)} labels, {dr.target.notna().sum()} resolved ({ocr_state}); manuals: {len(man)} model links, "
          f"{len(alarm_codes)} alarm codes, {len(failure_modes)} failure modes -> {path}")


if __name__ == "__main__":
    main()
