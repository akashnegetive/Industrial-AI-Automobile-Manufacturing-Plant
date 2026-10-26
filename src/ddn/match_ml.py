"""Part C2-C3, C7-C8 - ML entity matcher for tags and work orders.

Pipeline for each record (a tag or a work order):

  1. Candidates (blocking)  - never score all 455 assets. Union of:
       a. top-k assets by character n-gram TF-IDF similarity
       b. assets whose equipment code appears in the record (RB07, NR14, ...)
       c. the rules-matcher answer and, for WOs, the SAP equipment-number answer
       d. parent / children of those (robot <-> its weld gun)
     Blocking recall = share of records whose true asset is among the candidates.
  2. Pair features - does the candidate agree with what the record says?
       equipment / line / station / component match or conflict, text similarity,
       unit compatible with equipment type, agreement with rules / SAP number,
       optional sentence-embedding similarity.
  3. Classifier - LightGBM predicts P(candidate is the true asset).
       The record's answer is its best candidate; its probability is the confidence.
  4. Evaluation - 5-fold cross-validation grouped by record (out-of-fold
       predictions), so every TRAIN record is scored by a model that never saw it.
  5. Thresholds - read off the out-of-fold precision curve:
       auto-accept where precision >= 0.999, review queue down to where precision
       of the next band drops below 0.5, backlog below that.

Run:  python -m ddn.match_ml     (writes data/staging/links_*.parquet, reports/06_matching_ml.md)
"""
from __future__ import annotations

import re
import warnings

import lightgbm as lgb
import matplotlib
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupKFold

from .config import REPORTS, STAGING
from .evaluate import score
from .load import load
from .match_rules import STRUCTURAL, RulesMatcher, WorkOrderRulesMatcher
from .textnorm import Tokens, extract, split_name, translate

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)

TOP_K = 15
AUTO_PRECISION = 0.999     # auto-accept band: effectively zero wrong links out-of-fold.
                           # A wrong auto-link can send a recall investigation to the wrong robot;
                           # an extra record in the review queue costs an engineer a minute.
REVIEW_PRECISION = 0.50    # below this, a reviewer would mostly reject -> backlog

# Unit -> equipment types it can belong to (domain knowledge: kA fits a weld robot,
# Nm fits a nutrunner). Units not listed (degC, %, count...) carry no information.
UNIT_TYPES = {
    "kA": {"Robot", "WeldGun"}, "kN": {"Robot", "WeldGun"}, "Nm": {"Nutrunner", "ToolController"},
    "deg": {"Nutrunner", "ToolController"}, "degF": {"OvenZone", "AHU"}, "spm": {"Press"}, "t": {"Press"},
    "uS/cm": {"Tank"}, "pH": {"Tank"}, "l": {"Tank", "FillMachine"}, "cc/min": {"SealerRobot", "PaintRobot", "Dispenser"},
    "krpm": {"PaintRobot", "Atomizer"}, "kV": {"PaintRobot", "Atomizer", "Rectifier"}, "Nl/min": {"PaintRobot", "Atomizer"},
    "rpm": {"Fan", "Motor", "Pump"}, "mm/s": {"Fan", "Motor", "Pump", "Compressor"}, "%RH": {"AHU", "Humidifier"},
    "Pa": {"AHU"}, "Nm3/min": {"Compressor"}, "V": {"Rectifier"}, "m/min": {"Conveyor", "Press"},
}

FEATURES = ["tfidf", "fuzz_name", "fuzz_fl", "equip_match", "equip_conflict", "line_match", "line_conflict",
            "station_match", "station_conflict", "comp_match", "comp_conflict", "comp_parent", "shop_match",
            "unit_compat", "rule_match", "rule_conf", "eqno_match", "eqno_present", "fltext_match",
            "eqno_text_agree", "n_equip_cands", "is_component", "embed"]


# ------------------------------------------------------------------ assets
def asset_catalog(assets: pd.DataFrame) -> pd.DataFrame:
    """Equipment/component assets with tokens parsed from their FL path (reliable)."""
    a = assets[~assets.asset_type.isin(STRUCTURAL)].copy()
    rows = []
    for r in a.itertuples():
        segs = r.functional_location.split("-")[1:]
        rest = segs[2:]
        station = next((s for s in rest if re.fullmatch(r"ST\d{2}", s)), None)
        coded = [s for s in rest if re.search(r"\d", s) and not re.fullmatch(r"ST\d{2}", s)]
        alpha = [s for s in rest if not re.search(r"\d", s)]
        equip = coded[-1] if coded else (segs[1] if r.shop == "UTL" else None)
        comp = rest[-1] if rest and rest[-1] in alpha else None
        rows.append({"fl": r.functional_location, "shop": r.shop, "line": r.line if r.shop != "UTL" else None,
                     "station": station, "equip": equip, "comp": comp, "asset_type": r.asset_type,
                     "name": r.name, "parent": r.parent_fl,
                     "text": f"{' '.join(segs)} {r.name} {r.asset_type}".lower()})
    return pd.DataFrame(rows).set_index("fl", drop=False)


# ----------------------------------------------------------------- records
def tag_records(tags: pd.DataFrame, rules: pd.DataFrame) -> pd.DataFrame:
    r = tags.merge(rules[["tag_name", "functional_location", "method", "confidence"]], on="tag_name", how="left")
    out = pd.DataFrame({
        "record": r.tag_name,
        "text": (r.tag_name.map(split_name) + " " + r.description.fillna("")).str.lower(),
        "raw": r.tag_name.map(split_name) + " " + r.description.fillna(""),
        "shop": r.shop, "unit": r.unit,
        "rule_fl": r.functional_location, "rule_method": r.method, "rule_conf": r.confidence,
        "eqno_fl": None, "fltext_fl": None,
    })
    return out.set_index("record", drop=False)


def wo_records(wos: pd.DataFrame, rules: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    eq = assets.dropna(subset=["cmms_equipment_no"]).set_index("cmms_equipment_no").functional_location
    r = wos.merge(rules[["wo_number", "functional_location", "method", "confidence"]], on="wo_number", how="left")
    raw = (r.short_text.fillna("") + " " + r.long_text.fillna("") + " " + r.functional_location_text.fillna(""))
    fltext = r.functional_location.where(r.method.isin(["fl_text", "name"]))
    out = pd.DataFrame({
        "record": r.wo_number, "text": raw.map(translate).str.lower(), "raw": raw, "shop": None, "unit": None,
        # the SAP number is a *feature*, not a rule: it is wrong in ~4 % of cases
        "rule_fl": fltext, "rule_method": r.method.where(r.method.isin(["fl_text", "name"])),
        "rule_conf": r.confidence.where(r.method.isin(["fl_text", "name"])),
        "eqno_fl": r.equipment_no.map(eq), "fltext_fl": fltext,
    })
    return out.set_index("record", drop=False)


# --------------------------------------------------------------- candidates
class CandidateGenerator:
    def __init__(self, cat: pd.DataFrame, records: pd.DataFrame):
        self.cat = cat
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        self.vec.fit(pd.concat([cat.text, records.text]))
        self.A = self.vec.transform(cat.text)
        self.by_equip = cat.groupby("equip").fl.agg(list).to_dict()
        self.children = cat.groupby("parent").fl.agg(list).to_dict()

    def tfidf(self, texts: pd.Series) -> np.ndarray:
        return (self.vec.transform(texts) @ self.A.T).toarray()

    def generate(self, recs: pd.DataFrame, sims: np.ndarray, toks: dict[str, Tokens]) -> dict[str, set[str]]:
        fls = self.cat.index.to_numpy()
        out = {}
        for i, rec in enumerate(recs.itertuples()):
            cands = set(fls[np.argsort(-sims[i])[:TOP_K]])
            for e in toks[rec.record].equip:
                cands |= set(self.by_equip.get(e, []))
            cands |= {f for f in (rec.rule_fl, rec.eqno_fl) if isinstance(f, str) and f in self.cat.index}
            for f in list(cands):                       # robot <-> weld gun, nutrunner <-> controller
                cands |= set(self.children.get(f, []))
                p = self.cat.parent.get(f)
                if p in self.cat.index:
                    cands.add(p)
            out[rec.record] = cands
        return out


# ----------------------------------------------------------------- features
def _embedder():
    """Optional sentence-transformers similarity; returns None when unavailable (e.g. offline)."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


def pair_features(recs: pd.DataFrame, cands: dict[str, set[str]], cat: pd.DataFrame, sims: np.ndarray,
                  toks: dict[str, Tokens], embed=None) -> pd.DataFrame:
    col = {fl: j for j, fl in enumerate(cat.index)}
    rec_pos = {r: i for i, r in enumerate(recs.index)}
    E = None
    if embed is not None:
        er = embed.encode(recs.raw.tolist(), normalize_embeddings=True)
        ea = embed.encode(cat.text.tolist(), normalize_embeddings=True)
        E = er @ ea.T
    rows = []
    for rec in recs.itertuples():
        t = toks[rec.record]
        cs = sorted(cands[rec.record])     # sets have no stable order across runs -> sort for reproducibility
        n_eq = sum(cat.at[f, "equip"] in t.equip for f in cs)
        # Does the text confirm the SAP equipment number? 1 agree, 0 contradict, -1 cannot tell.
        # This lets the model learn *when* to distrust the number (wrong in ~4 % of WOs).
        if isinstance(rec.eqno_fl, str) and rec.eqno_fl in cat.index and t.equip:
            eq_agree = int(cat.at[rec.eqno_fl, "equip"] in t.equip)
        else:
            eq_agree = -1
        for f in cs:
            a = cat.loc[f]
            types = UNIT_TYPES.get(rec.unit) if isinstance(rec.unit, str) else None
            rows.append({
                "record": rec.record, "fl": f,
                "tfidf": sims[rec_pos[rec.record], col[f]],
                "fuzz_name": fuzz.token_set_ratio(rec.raw.lower(), a["name"].lower()) / 100,
                "fuzz_fl": fuzz.partial_ratio(rec.text.replace(" ", ""), f.lower().replace("-", "")) / 100,
                "equip_match": int(a.equip in t.equip),
                "equip_conflict": int(bool(t.equip) and a.equip not in t.equip),
                "line_match": int(a.line in t.lines),
                "line_conflict": int(bool(t.lines) and a.line is not None and a.line not in t.lines),
                "station_match": int(a.station in t.stations),
                "station_conflict": int(bool(t.stations) and a.station is not None and a.station not in t.stations),
                "comp_match": int(a.comp is not None and a.comp in t.comps),
                "comp_conflict": int(a.comp is not None and a.comp not in t.comps),
                "comp_parent": int(a.comp is None and bool(t.comps)),
                "shop_match": -1 if not isinstance(rec.shop, str) else int(rec.shop == a.shop),
                "unit_compat": -1 if types is None else int(a.asset_type in types),
                "rule_match": int(rec.rule_fl == f),
                "rule_conf": float(rec.rule_conf) if rec.rule_fl == f else 0.0,
                "eqno_match": int(rec.eqno_fl == f),
                "eqno_present": int(isinstance(rec.eqno_fl, str)),
                "fltext_match": int(rec.fltext_fl == f),
                "eqno_text_agree": eq_agree,
                "n_equip_cands": n_eq,
                "is_component": int(a.comp is not None),
                "embed": float(E[rec_pos[rec.record], col[f]]) if E is not None else np.nan,
            })
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- model
def make_model() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                              subsample=0.9, colsample_bytree=0.9, random_state=7, verbose=-1)


def best_per_record(pairs: pd.DataFrame, prob: np.ndarray) -> pd.DataFrame:
    # ties (e.g. "R7" -> robot 7 on L1, L2 and L3 equally likely) are broken by FL so runs are reproducible
    p = pairs[["record", "fl"]].assign(prob=prob).sort_values(["record", "prob", "fl"], ascending=[True, False, True],
                                                              kind="mergesort")
    top = p.groupby("record").head(2)
    first = top.groupby("record").first()
    second = top.groupby("record").prob.nth(1).groupby(level=0).first() if len(top) else pd.Series(dtype=float)
    first["margin"] = first.prob - second.reindex(first.index).fillna(0)
    return first.reset_index().rename(columns={"fl": "functional_location", "prob": "confidence"})


def cross_validate(pairs: pd.DataFrame, truth: dict[str, str], folds: int = 5) -> pd.DataFrame:
    lab = pairs[pairs.record.isin(truth)].copy()
    lab["y"] = (lab.fl == lab.record.map(truth)).astype(int)
    oof = np.zeros(len(lab))
    for tr, te in GroupKFold(n_splits=folds).split(lab, lab.y, lab.record):
        m = make_model().fit(lab.iloc[tr][FEATURES], lab.iloc[tr].y)
        oof[te] = m.predict_proba(lab.iloc[te][FEATURES])[:, 1]
    return best_per_record(lab, oof)


def thresholds(oof: pd.DataFrame, truth: dict[str, str]) -> tuple[float, float, pd.DataFrame]:
    """Read auto-accept and review thresholds off the out-of-fold precision curve."""
    d = oof.assign(correct=oof.functional_location == oof.record.map(truth)).sort_values("confidence", ascending=False)
    d["cum_precision"] = d.correct.cumsum() / np.arange(1, len(d) + 1)
    d["recall"] = d.correct.cumsum() / len(d)
    ok = d[d.cum_precision >= AUTO_PRECISION]
    t_auto = float(ok.confidence.min()) if len(ok) else 1.0
    below = d[d.confidence < t_auto].copy()
    # walk down in bands of 20 records; stop where a band's precision falls below REVIEW_PRECISION
    t_review = t_auto
    for start in range(0, len(below), 20):
        band = below.iloc[start:start + 20]
        if band.correct.mean() < REVIEW_PRECISION:
            break
        t_review = float(band.confidence.min())
    return max(t_auto, 0.5), min(t_review, max(t_auto, 0.5)), d


def band_of(conf: float, t_auto: float, t_review: float) -> str:
    return "auto_accept" if conf >= t_auto else "review" if conf >= t_review else "backlog"


# --------------------------------------------------------------------- runner
def run_source(name: str, recs: pd.DataFrame, truth: dict[str, str], cat: pd.DataFrame, embed) -> dict:
    toks = {r.record: extract(r.raw) for r in recs.itertuples()}
    gen = CandidateGenerator(cat, recs)
    sims = gen.tfidf(recs.text)
    cands = gen.generate(recs, sims, toks)
    labelled = [r for r in recs.index if r in truth]
    block_recall = np.mean([truth[r] in cands[r] for r in labelled])
    pairs = pair_features(recs, cands, cat, sims, toks, embed)

    oof = cross_validate(pairs, truth)
    t_auto, t_review, curve = thresholds(oof, truth)

    lab = pairs[pairs.record.isin(truth)].assign(y=lambda d: (d.fl == d.record.map(truth)).astype(int))
    model = make_model().fit(lab[FEATURES], lab.y)
    final = best_per_record(pairs, model.predict_proba(pairs[FEATURES])[:, 1])
    final["band"] = [band_of(c, t_auto, t_review) for c in final.confidence]
    final["method"] = "ml"
    imp = pd.Series(model.booster_.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
    return dict(name=name, recs=recs, cands=cands, pairs=pairs, oof=oof, final=final, curve=curve,
                t_auto=t_auto, t_review=t_review, block_recall=block_recall,
                n_pairs=len(pairs), avg_cands=len(pairs) / len(recs), importance=imp)


def plot_curve(res: dict, path) -> None:
    c = res["curve"]
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    ax.plot(c.recall, c.cum_precision, color="#2a6fdb", lw=2)
    for t, lab, col in [(res["t_auto"], "auto-accept", "#1b8a3a"), (res["t_review"], "review", "#d08c00")]:
        row = c[c.confidence >= t].tail(1)
        if len(row):
            ax.scatter(row.recall, row.cum_precision, color=col, zorder=3, label=f"{lab} t={t:.2f}")
    ax.set_xlabel("recall (share of records auto-linked correctly)")
    ax.set_ylabel("precision")
    ax.set_ylim(min(0.8, c.cum_precision.min() - 0.02), 1.005)
    ax.set_title(f"{res['name']}: out-of-fold precision-recall")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    tags = pd.read_parquet(STAGING / "tags.parquet")
    assets = pd.read_parquet(STAGING / "assets.parquet")
    cat = asset_catalog(assets)
    embed = _embedder()

    tag_truth = dict(load("labels_tag_to_asset_TRAIN.csv").values)
    wos = load("maintenance_work_orders.csv")
    wo_truth = dict(load("labels_workorder_to_asset_TRAIN.csv").values)

    tag_rules = RulesMatcher(assets).match_all(tags)
    wo_rules = WorkOrderRulesMatcher(assets).match_all(wos)

    results = [
        (run_source("Tags", tag_records(tags, tag_rules), tag_truth, cat, embed), tag_rules, "tag_name", tag_truth),
        (run_source("Work orders", wo_records(wos, wo_rules, assets), wo_truth, cat, embed), wo_rules, "wo_number",
         wo_truth),
    ]
    fig_dir = REPORTS / "figures"
    fig_dir.mkdir(exist_ok=True)

    out = ["# Part C – ML matcher vs rules-only baseline", "",
           "Generated by `python -m ddn.match_ml`. ML scores are **out-of-fold**: 5-fold cross-validation grouped by "
           "record, so each TRAIN record is predicted by a model that never saw its label.", "",
           f"Sentence-embedding feature: **{'on' if embed else 'off'}** "
           f"({'all-MiniLM-L6-v2' if embed else 'sentence-transformers or its model not available; feature left empty'}).",
           "", "## Summary", "",
           "| Source | Method | Precision | Recall | F1 | Wrong links |", "|---|---|---:|---:|---:|---:|"]
    detail = []
    for res, rules, key, truth in results:
        t = pd.DataFrame(list(truth.items()), columns=[key, "functional_location"])
        rs = score(rules, t, key)
        oof = res["oof"].rename(columns={"record": key})
        ms = score(oof, t, key)
        auto = oof[oof.confidence >= res["t_auto"]]
        auto_s = score(auto, t[t[key].isin(auto[key])], key)
        out.append(f"| {res['name']} | rules only | {rs['precision']:.3f} | {rs['recall']:.3f} | {rs['f1']:.3f} | {rs['fp']} |")
        out.append(f"| {res['name']} | ML (top candidate) | {ms['precision']:.3f} | {ms['recall']:.3f} | {ms['f1']:.3f} | {ms['fp']} |")
        out.append(f"| {res['name']} | ML auto-accept band only | {auto_s['precision']:.3f} | "
                   f"{auto_s['tp'] / len(t):.3f} | — | {auto_s['fp']} |")

        plot_curve(res, fig_dir / f"pr_{key}.png")
        final = res["final"].rename(columns={"record": key})
        final.to_parquet(STAGING / f"links_{key}.parquet", index=False)
        bands = final.band.value_counts()
        m = oof.merge(t, on=key, suffixes=("_pred", "_true"))
        wrong = m[m.functional_location_pred != m.functional_location_true].sort_values("confidence", ascending=False)
        rules_m = rules[[key, "functional_location"]].rename(columns={"functional_location": "functional_location_rule"})
        fixed = m.merge(rules_m, on=key)
        fixed = fixed[(fixed.functional_location_pred == fixed.functional_location_true) &
                      (fixed.functional_location_rule != fixed.functional_location_true)]
        broke = m.merge(rules_m, on=key)
        broke = broke[(broke.functional_location_pred != broke.functional_location_true) &
                      (broke.functional_location_rule == broke.functional_location_true)]
        detail += [f"## {res['name']}", "",
                   f"- Records: {len(res['recs']):,}; candidate pairs: {res['n_pairs']:,} "
                   f"(avg {res['avg_cands']:.1f} per record instead of {len(cat)})",
                   f"- **Blocking recall: {res['block_recall']:.3f}** (true asset is among the candidates)",
                   f"- Thresholds from the precision curve: auto-accept ≥ **{res['t_auto']:.2f}**, "
                   f"review ≥ **{res['t_review']:.2f}**, backlog below",
                   f"- All {len(final):,} records: auto-accept {bands.get('auto_accept', 0):,}, "
                   f"review {bands.get('review', 0):,}, backlog {bands.get('backlog', 0):,}",
                   f"- ML fixed {len(fixed)} records the rules got wrong or missed; "
                   f"ML broke {len(broke)} records the rules got right", "",
                   f"![PR curve](figures/pr_{key}.png)", "",
                   "Top features (LightGBM gain): " + ", ".join(f"`{k}`" for k in res["importance"].head(8).index), "",
                   "Threshold trade-off (out-of-fold, labelled records):", "",
                   "| Auto-accept threshold | Auto-linked | Wrong | Precision | Share of records auto-linked correctly |",
                   "|---:|---:|---:|---:|---:|"]
        ok = oof.functional_location == oof[key].map(truth)
        for thr in [0.5, 0.7, 0.8, 0.85, 0.9, 0.95]:
            sel = oof.confidence >= thr
            detail.append(f"| {thr:.2f}{' (chosen)' if abs(thr - res['t_auto']) < 0.025 else ''} | {sel.sum()} | "
                          f"{(sel & ~ok).sum()} | {ok[sel].mean():.4f} | {(sel & ok).sum() / len(oof):.3f} |")
        detail += ["", f"### Out-of-fold errors ({len(wrong)})", "",
                   "| Record | Confidence | Predicted | Truth | Text |", "|---|---:|---|---|---|"]
        txt = res["recs"].raw
        detail += [f"| `{r[key]}` | {r.confidence:.2f} | `{r.functional_location_pred}` | "
                   f"`{r.functional_location_true}` | {txt.get(r[key], '')[:70]} |" for _, r in wrong.head(25).iterrows()]
        detail += [""]
    path = REPORTS / "06_matching_ml.md"
    path.write_text("\n".join(out + [""] + detail), encoding="utf-8")
    for res, *_ in results:
        print(f"{res['name']}: blocking recall {res['block_recall']:.3f}, thresholds auto {res['t_auto']:.2f} "
              f"review {res['t_review']:.2f}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
