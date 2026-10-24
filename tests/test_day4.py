"""Day 4: tag parsing, rules matchers, evaluation maths."""
import pandas as pd
import pytest

from ddn.evaluate import score
from ddn.load import load
from ddn.match_rules import RulesMatcher, WorkOrderRulesMatcher
from ddn.tags import parse_tag, stage_assets, stage_tags


@pytest.mark.parametrize("name,source,expected", [
    ("DDN1_BIW_L2_R07_WELDCUR.PV", "PI Historian", ("BIW", "L2", "RB07", "WELDCUR")),
    ("PaintShop-Ovn02-Z3-Temp", "WinCC SCADA", ("PNT", "OV2", "Z3", "TEMP")),
    ("PaintShop-AirHandling-AHUTC2HUM-Valve", "WinCC SCADA", ("PNT", "AHU", "AHUTC2HUM", "VALVE")),
    ("PRS.PL1.PR1HOL.CUR", "S7 legacy OPC", ("PRS", "PL1", "PR1HOL", "CUR")),
    ("FA_EOL_P1_RUNHRS", "MES", ("ASM", "EOL", "P1", "RUNHRS")),
])
def test_parse_tag(name, source, expected):
    p = parse_tag(name, source)
    assert p["parsed"] and (p["shop"], p["line"], p["equip"], p["signal"]) == expected


def test_typo_tag_is_not_parsed():
    assert not parse_tag("DN1_BIW_L1_R04_WELDCNT.PV", "PI Historian")["parsed"]


@pytest.fixture(scope="module")
def staged():
    return stage_tags(), stage_assets()


def test_relocated_robot_resolves_to_new_line(staged):
    tags, assets = staged
    tag = tags[tags.tag_name == "DDN1_BIW_L1ST3_RB5_WELDCUR.PV"].iloc[0]
    m = RulesMatcher(assets).match(tag)
    assert m.functional_location == "DDN1-BIW-L2-ST06-RB12" and m.method == "relocation"


def test_zero_padding_tries_both_forms(staged):
    tags, assets = staged
    rm = RulesMatcher(assets)
    for name, fl in [("FA_EOL_P1_RUNHRS", "DDN1-ASM-EOL-WT-P1"), ("FA_CH1_AGV7_BATT", "DDN1-ASM-CH1-AGV07")]:
        assert rm.match(tags[tags.tag_name == name].iloc[0]).functional_location == fl


def test_rules_baseline_never_links_wrongly_on_train(staged):
    tags, assets = staged
    s = score(RulesMatcher(assets).match_all(tags), load("labels_tag_to_asset_TRAIN.csv"))
    assert s["fp"] == 0 and s["f1"] > 0.95


def test_workorder_equipment_number_is_not_ground_truth(staged):
    _, assets = staged
    pred = WorkOrderRulesMatcher(assets).match_all(load("maintenance_work_orders.csv"))
    s = score(pred, load("labels_workorder_to_asset_TRAIN.csv"), key="wo_number")
    assert s["fp"] > 0            # wrong SAP numbers -> wrong links: why ML/text cross-checks are needed


def test_score_counts_wrong_link_as_fp_and_fn():
    truth = pd.DataFrame({"tag_name": ["a", "b", "c"], "functional_location": ["X", "Y", "Z"]})
    pred = pd.DataFrame({"tag_name": ["a", "b", "c"], "functional_location": ["X", "WRONG", None]})
    s = score(pred, truth)
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 2)
    assert s["precision"] == 0.5 and round(s["recall"], 3) == 0.333
