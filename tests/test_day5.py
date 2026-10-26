"""Day 5: text normalisation, candidate generation and threshold logic (fast tests, no full CV)."""
import pandas as pd
import pytest

from ddn.match_ml import CandidateGenerator, asset_catalog, thresholds, wo_records
from ddn.match_rules import WorkOrderRulesMatcher
from ddn.tags import stage_assets
from ddn.textnorm import extract, split_name


@pytest.mark.parametrize("text,expected", [
    ("R7 gun tip dressing fail, cap changed", {"RB07", "WG"}),
    ("robot no 4 L2 gun water leak at cap adaptor", {"L2", "RB04", "WG"}),
    ("DC tool 14 spindle not running", {"NR14"}),
    ("Sealer robo 3 nozzle not heating", {"SR03"}),           # not RB03: Hinglish 'robo' handled first
    ("pump P-104 trip ho raha hai", {"P104"}),
    ("Chiller CH-01 low refrigerant", {"CH01"}),               # chiller, not the CH1 chassis line
    ("tip dresser Station 01 L3 blade broken", {"L3", "ST01", "TD"}),
])
def test_extract_tokens(text, expected):
    assert set(extract(text).as_text().split()) == expected


def test_split_name_unglues_codes():
    assert split_name("PaintShop-Ovn02-Z3FAN-Spd") == "PaintShop Ovn02 Z3 FAN Spd"


@pytest.fixture(scope="module")
def catalog():
    assets = stage_assets()
    return assets, asset_catalog(assets)


def test_asset_catalog_tokens(catalog):
    _, cat = catalog
    wg = cat.loc["DDN1-BIW-L2-ST04-RB07-WG"]
    assert (wg.line, wg.station, wg.equip, wg.comp) == ("L2", "ST04", "RB07", "WG")
    assert cat.loc["DDN1-UTL-CMP02"].equip == "CMP02"


def test_candidates_include_all_lines_when_text_has_no_line(catalog):
    assets, cat = catalog
    wos = pd.DataFrame([{"wo_number": "X1", "short_text": "R7 dress pack cable damaged", "long_text": None,
                         "functional_location_text": None, "equipment_no": None}])
    recs = wo_records(wos, WorkOrderRulesMatcher(assets).match_all(wos), assets)
    gen = CandidateGenerator(cat, recs)
    cands = gen.generate(recs, gen.tfidf(recs.text), {"X1": extract(recs.raw.iloc[0])})["X1"]
    assert {"DDN1-BIW-L1-ST04-RB07", "DDN1-BIW-L2-ST04-RB07", "DDN1-BIW-L3-ST04-RB07"} <= cands


def test_auto_threshold_excludes_wrong_links():
    oof = pd.DataFrame({"record": list("abcdef"), "functional_location": ["A", "B", "C", "X", "E", "F"],
                        "confidence": [0.99, 0.97, 0.95, 0.80, 0.70, 0.60]})
    truth = dict(zip("abcdef", "ABCDEF"))            # 'd' (conf 0.80) is wrong
    t_auto, _, _ = thresholds(oof, truth)
    assert t_auto > 0.80                              # the wrong link must not be auto-accepted
