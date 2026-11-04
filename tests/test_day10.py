"""Day 10: deliverables - hidden-test predictions, the demo helper, the notebook."""
import json
from pathlib import Path

import pandas as pd
import pytest

from ddn import export, graph
from ddn.config import ROOT, STAGING

NEED_STAGING = pytest.mark.skipif(not (STAGING / "links_tag_name.parquet").exists(), reason="run the pipeline first")


@NEED_STAGING
def test_every_record_gets_one_prediction_with_band():
    for links, key, train, kind, _ in export.SOURCES:
        p = export.predictions(links, key, train, kind)
        assert p[key].is_unique and p.functional_location.notna().all()
        assert set(p.band) <= {"auto_accept", "review", "backlog"}
        assert p.in_train.any() and (~p.in_train).any()


@NEED_STAGING
def test_tag_predictions_cover_all_1541_tags():
    p = export.predictions(*export.SOURCES[0][:4])
    assert len(p) == 1541


def test_notebook_has_run_without_errors():
    nb = json.loads((ROOT / "notebooks" / "01_data_profiling.ipynb").read_text(encoding="utf-8"))
    outputs = [o for c in nb["cells"] if c["cell_type"] == "code" for o in c.get("outputs", [])]
    assert outputs and not [o for o in outputs if o.get("output_type") == "error"]


@pytest.mark.skipif(not graph.neo4j_available(wait_s=0), reason="Neo4j not running (docker compose up -d)")
def test_demo_stories_run(capsys):
    from ddn import demo
    demo.tag_story("DDN1_BIW_L2_R07_WELDCUR.PV")
    demo.vin_story(None)
    out = capsys.readouterr().out
    assert "DDN1-BIW-L2-ST04-RB07" in out and "causedBy AN-003" in out


# ------------------------------------------------------------------ three-band gate (backlog)
def test_backlog_threshold_only_where_low_scores_were_mostly_wrong():
    from ddn import match_ml as M
    cat = pd.DataFrame({"parent": {}})
    recs = [f"r{i}" for i in range(12)]
    conf = [0.99] * 6 + [0.5, 0.4, 0.03, 0.02, 0.01, 0.005]
    right = [True] * 8 + [False] * 4                       # the four lowest scores are wrong
    oof = pd.DataFrame({"record": recs, "confidence": conf,
                        "functional_location": ["A" if r else "B" for r in right]})
    truth = {r: "A" for r in recs}
    t_auto, t_review, _ = M.thresholds(oof, truth, cat.assign(parent=pd.Series(dtype=str)))
    assert t_review > 0.03 and t_review <= t_auto           # backlog = the four wrong ones
    oof2 = oof.assign(functional_location="A")              # low scores but all right -> no backlog
    assert M.thresholds(oof2, truth, cat.assign(parent=pd.Series(dtype=str)))[1] == 0.0


@NEED_STAGING
def test_review_queue_pulls_anomaly_work_orders_from_backlog_and_adds_link_prediction():
    from ddn.review import build_queue
    if not (STAGING / "link_suggestions.parquet").exists():
        pytest.skip("run python -m ddn.linkpred first")
    q = build_queue()
    assert q.iloc[0].explains_anomaly                        # anomaly-explaining items first
    assert q.item_id.str.startswith("e3:").any()             # E3 suggestions routed to review
    links = q[q.kind.isin(["tag", "workorder"])]
    assert not links.record.duplicated().any()               # one item per tag / work order


# ------------------------------------------------------------------ E3 link prediction
@NEED_STAGING
def test_link_prediction_learns_from_approved_links():
    from ddn import linkpred as L
    assets = pd.read_parquet(STAGING / "assets.parquet")
    recs = L.records()
    lp = L.LinkPredictor(assets, recs)
    wo = "4100629"                                           # "Station 04 L2 fixture locating pin worn"
    top = [fl for fl, _ in lp.fit(L.approved_links(recs)).suggest(wo, k=3)]
    assert "DDN1-BIW-L2-ST04-FX" in top
