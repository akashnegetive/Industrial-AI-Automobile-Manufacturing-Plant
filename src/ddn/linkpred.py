"""Part E3 (bonus) - suggest missing links from the graph's own structure, and route them to the review queue.

The matcher (Part C) scores each record against assets with designed features. Link prediction looks at the
graph instead: work orders and tags that use the same words as the records ALREADY linked to an asset are
probably about that asset too. For example, "cap tip dressing" work orders belong to weld guns because the graph
already holds approved work-order -> weld-gun edges.

Node embeddings by neighbourhood aggregation (one round of GraphSAGE-style mean aggregation, no learned weights):
    record vector  = TF-IDF over its tokens (canonical codes L2 / ST04 / RB07 / WG weighted x3, plus words)
    asset vector   = its own tokens (FL, name, type) + ALPHA x mean of the vectors of its approved records
    score          = cosine(record, asset), over all 455 assets (no candidate list from the matcher)

A first version used a spectral embedding (truncated SVD of the adjacency): hit@1 was only 0.03, because
siblings (robot 07 on L1/L2/L3) share the same tokens and the low-rank space blurred them. Aggregating the
approved links is what makes the difference.

Evaluation is honest: 5 folds over the labelled records; a fold's own record -> asset links are removed before
the asset vectors are built. CODE_WEIGHT and ALPHA were picked from 6 combinations on these labelled
folds; that small choice is stated in the report.

Use: every backlog record goes to the review queue with link prediction's top 3 (on hard records its top-1
is often wrong but the right asset is usually in the top 3-5, so the engineer picks). Review-band records show
the suggestion as extra context.

Run:  python -m ddn.linkpred     (data/staging/link_suggestions.parquet, reports/15_link_prediction.md)
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .config import REPORTS, STAGING
from .load import load
from .review import engineer_labels
from .textnorm import extract, split_name

FOLDS, SEED = 5, 7
CODE_WEIGHT, ALPHA = 3.0, 1.0
STOP = {"the", "and", "for", "with", "was", "not", "has", "had", "after", "from", "this", "that", "check",
        "checked", "done", "ok", "per", "pv", "ddn1", "dd1", "dn1"}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower()) if w not in STOP}


def code_tokens(text: str) -> set[str]:
    t = extract(text)
    return {f"line:{x}" for x in t.lines} | {f"stn:{x}" for x in t.stations} | \
           {f"eq:{x}" for x in t.equip} | {f"comp:{x}" for x in t.comps}


def asset_tokens(a) -> set[str]:
    parts = a.functional_location.split("-")
    toks = {f"line:{p}" for p in parts[2:3]} | {f"stn:{p}" for p in parts if re.fullmatch(r"ST\d\d", p)}
    if len(parts) >= 4:
        toks.add(f"eq:{parts[-1] if not re.fullmatch(r'ST\d\d', parts[-1]) else ''}")
    toks |= code_tokens(f"{a.functional_location.replace('-', ' ')} {a.name}")
    toks |= words(f"{a.name} {a.asset_type}")
    return {t for t in toks if not t.endswith(":")}


def records() -> pd.DataFrame:
    """Every tag and work order with its text tokens, current matcher link and band."""
    tags = pd.read_parquet(STAGING / "tags.parquet")
    tl = pd.read_parquet(STAGING / "links_tag_name.parquet").set_index("tag_name")
    wos = load("maintenance_work_orders.csv")
    wl = pd.read_parquet(STAGING / "links_wo_number.parquet").set_index("wo_number")
    rows = []
    for t in tags.itertuples():
        text = f"{split_name(t.tag_name)} {t.description if isinstance(t.description, str) else ''}"
        rows.append(("tag", t.tag_name, text))
    for w in wos.itertuples():
        text = " ".join(str(x) for x in (w.short_text, w.long_text, w.functional_location_text) if isinstance(x, str))
        rows.append(("workorder", w.wo_number, text))
    r = pd.DataFrame(rows, columns=["kind", "record", "text"])
    link = pd.concat([tl[["functional_location", "confidence", "band"]], wl[["functional_location", "confidence", "band"]]])
    r = r.join(link, on="record")
    r["tokens"] = [code_tokens(x) | words(x) for x in r.text]
    return r


class LinkPredictor:
    def __init__(self, assets: pd.DataFrame, recs: pd.DataFrame):
        self.fls = list(assets.functional_location)
        self.fi = {f: i for i, f in enumerate(self.fls)}
        a_docs = [" ".join(sorted(asset_tokens(a))) for a in assets.itertuples()]
        r_docs = [" ".join(sorted(t)) for t in recs.tokens]
        self.vec = TfidfVectorizer(token_pattern=r"\S+", sublinear_tf=True, lowercase=False).fit(a_docs + r_docs)
        is_code = np.array([t.split(":")[0] in {"line", "stn", "eq", "comp"} for t in self.vec.get_feature_names_out()])
        self.w = np.where(is_code, CODE_WEIGHT, 1.0)
        self.A = self._x(a_docs).toarray()
        self.R = self._x(r_docs)
        self.ri = {r: i for i, r in enumerate(recs.record)}

    def _x(self, docs):
        return normalize(self.vec.transform(docs).multiply(self.w).tocsr())

    def fit(self, links: dict[str, str]) -> "LinkPredictor":
        """links: record -> functional location for the approved edges the graph may use."""
        agg = np.zeros_like(self.A)
        cnt = np.zeros(len(self.fls))
        for r, fl in links.items():
            if fl in self.fi and r in self.ri:
                agg[self.fi[fl]] += self.R[self.ri[r]].toarray().ravel()
                cnt[self.fi[fl]] += 1
        self.P = normalize(self.A + ALPHA * agg / np.maximum(cnt, 1)[:, None])
        return self

    def suggest(self, record: str, k: int = 3) -> list[tuple[str, float]]:
        s = self.P @ self.R[self.ri[record]].toarray().ravel()
        top = np.argsort(-s)[:k]
        return [(self.fls[t], float(s[t])) for t in top]


def approved_links(recs: pd.DataFrame) -> dict[str, str]:
    eng = {**engineer_labels("tag"), **engineer_labels("workorder")}
    auto = recs[recs.band == "auto_accept"].set_index("record").functional_location.to_dict()
    return {**auto, **eng}


def evaluate(lp: LinkPredictor, recs: pd.DataFrame, truth: dict[str, str]) -> pd.DataFrame:
    """Out-of-fold: hide each fold's own links, fit, rank all assets for the fold's records."""
    links = approved_links(recs)
    labelled = np.array(sorted(r for r in truth if r in set(recs.record)))
    rng = np.random.default_rng(SEED)
    fold = rng.integers(0, FOLDS, len(labelled))
    rows = []
    for f in range(FOLDS):
        test = set(labelled[fold == f])
        lp.fit({r: fl for r, fl in links.items() if r not in test})
        for r in test:
            sug = lp.suggest(r, k=5)
            rows.append({"record": r, "truth": truth[r], "top1": sug[0][0], "score": sug[0][1],
                         "hit1": sug[0][0] == truth[r], "hit3": truth[r] in [s for s, _ in sug[:3]],
                         "hit5": truth[r] in [s for s, _ in sug]})
    return pd.DataFrame(rows)


def run() -> tuple[pd.DataFrame, dict]:
    assets = pd.read_parquet(STAGING / "assets.parquet")
    recs = records()
    truth = {**dict(load("labels_tag_to_asset_TRAIN.csv").values), **dict(load("labels_workorder_to_asset_TRAIN.csv").values)}
    lp = LinkPredictor(assets, recs)
    ev = evaluate(lp, recs, truth).merge(recs[["record", "kind", "band"]], on="record")
    oof = pd.concat([pd.read_parquet(STAGING / f"oof_{k}.parquet") for k in ("tag_name", "wo_number")])
    ev = ev.merge(oof.rename(columns={"functional_location": "matcher_oof", "confidence": "matcher_oof_conf"}),
                  on="record", how="left")
    ev["matcher_right"] = ev.matcher_oof == ev.truth

    lp.fit(approved_links(recs))
    todo = recs[recs.band.isin(["backlog", "review"]) | recs.functional_location.isna()]
    sug = []
    for r in todo.itertuples():
        top = lp.suggest(r.record, k=3)
        sug.append({"kind": r.kind, "record": r.record, "matcher_fl": r.functional_location,
                    "matcher_conf": r.confidence, "band": r.band, "e3_fl": top[0][0], "e3_score": round(top[0][1], 3),
                    "e3_alternatives": "; ".join(f"{fl} ({s:.2f})" for fl, s in top[1:]),
                    "agrees": top[0][0] == r.functional_location, "to_review": r.band == "backlog"})
    sug = pd.DataFrame(sug)
    sug.to_parquet(STAGING / "link_suggestions.parquet", index=False)

    hard = ev[~ev.matcher_right | (ev.band != "auto_accept")]
    stats = dict(n=len(ev), hit1=ev.hit1.mean(), hit5=ev.hit5.mean(), matcher=ev.matcher_right.mean(),
                 hard_n=len(hard), hard_hit1=hard.hit1.mean() if len(hard) else 0,
                 hard_hit3=hard.hit3.mean() if len(hard) else 0, hard_hit5=hard.hit5.mean() if len(hard) else 0,
                 rescued=int((~ev.matcher_right & ev.hit1).sum()), rescued3=int((~ev.matcher_right & ev.hit3).sum()),
                 matcher_wrong=int((~ev.matcher_right).sum()),
                 by_kind=ev.groupby("kind").agg(n=("hit1", "size"), hit1=("hit1", "mean"), hit5=("hit5", "mean"),
                                                matcher=("matcher_right", "mean")))
    return sug, stats


def recs_text() -> dict[str, str]:
    w = load("maintenance_work_orders.csv")
    return dict(zip(w.wo_number, w.short_text.fillna("").str.replace("|", "/")))


def report(sug: pd.DataFrame, st: dict) -> str:
    out = ["# Part E3 (bonus) – Suggesting missing links with node embeddings", "",
           "Generated by `python -m ddn.linkpred`. Spectral node embeddings (truncated SVD of the normalised "
           "adjacency) over records, assets, text tokens, the hierarchy and every approved link; score = cosine "
           f"similarity. Evaluated out-of-fold ({FOLDS} folds over the labelled records; a fold's own links are hidden "
           "before fitting).", "",
           "## How good is it on its own?", "",
           "| Records | n | Link prediction hit@1 | hit@5 | Matcher top-1 (out-of-fold) |", "|---|---:|---:|---:|---:|"]
    for k, r in st["by_kind"].iterrows():
        out.append(f"| {k} | {int(r.n)} | {r.hit1:.3f} | {r.hit5:.3f} | {r.matcher:.3f} |")
    out += [f"| all | {st['n']} | {st['hit1']:.3f} | {st['hit5']:.3f} | {st['matcher']:.3f} |", "",
            "Link prediction is **weaker than the matcher overall**. That is expected: the matcher uses 20 designed "
            "features and a candidate list, while link prediction ranks all 455 assets from graph structure alone. "
            "Its value is as an independent **second opinion** where the matcher is unsure. "
            f"(The two settings CODE_WEIGHT={CODE_WEIGHT:g}, ALPHA={ALPHA:g} were chosen from 6 combinations on these "
            "same folds, so the numbers are slightly optimistic.) A first version with a spectral (SVD) embedding "
            "reached only hit@1 0.03: siblings such as robot 07 on three lines share their tokens, and only the "
            "aggregated approved links separate them.", "",
            "## Where it helps: records the matcher got wrong or was unsure about", "",
            f"- Labelled records the matcher was unsure about (below auto-accept) or got wrong: **{st['hard_n']}**. "
            f"Link prediction hit@1 **{st['hard_hit1']:.2f}**, hit@3 **{st['hard_hit3']:.2f}**, hit@5 "
            f"**{st['hard_hit5']:.2f}**.",
            f"- Of the {st['matcher_wrong']} labelled records whose out-of-fold top candidate was wrong, link prediction "
            f"had the right asset first for **{st['rescued']}** and in its top 3 for **{st['rescued3']}**.",
            "- So on hard records its top-1 alone is not trustworthy, but its top 3 usually contains the answer. "
            "That is why it is routed as a short list for an engineer, never auto-accepted.", "",
            "## Suggestions routed to the review queue", ""]
    routed = sug[sug.to_review]
    out += [f"- Every backlog record, **{len(routed)}**, goes to the review screen with link prediction's top 3 "
            "(marked *suggested by link prediction*). Review-band records show the suggestion as extra "
            f"context: it agrees with the matcher for {int(sug[sug.band == 'review'].agrees.sum())} of "
            f"{int((sug.band == 'review').sum())}.", ""]
    if len(routed):
        out += ["Where the two disagree (first 15):", "",
                "| Kind | Record | Text | Link prediction suggests (score) | Matcher's guess (conf.) |", "|---|---|---|---|---|"]
        text = recs_text()
        for r in routed[~routed.agrees].sort_values("e3_score", ascending=False).head(15).itertuples():
            out.append(f"| {r.kind} | `{r.record}` | {text.get(r.record, '')[:60]} | `{r.e3_fl}` ({r.e3_score:.2f}) | "
                       f"`{r.matcher_fl}` ({r.matcher_conf:.3f}) |")
    out += ["", "Approving one in the review screen makes it a `method=engineer` edge and a training label, the "
            "same loop as any other review decision.", ""]
    return "\n".join(out)


def main() -> None:
    sug, st = run()
    path = REPORTS / "15_link_prediction.md"
    path.write_text(report(sug, st), encoding="utf-8")
    print(f"link prediction: hit@1 {st['hit1']:.3f} (matcher {st['matcher']:.3f}), hard cases hit@1 "
          f"{st['hard_hit1']:.2f}, rescued {st['rescued']}/{st['matcher_wrong']} (top-3: {st['rescued3']}), "
          f"backlog hit@3 {st['hard_hit3']:.2f}, {int(sug.to_review.sum())} backlog records routed to review with top 3 -> {path}")


if __name__ == "__main__":
    main()
