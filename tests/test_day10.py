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
