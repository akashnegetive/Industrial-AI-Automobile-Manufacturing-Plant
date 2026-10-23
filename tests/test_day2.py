"""Day 2 tests: the key findings must not silently disappear when code changes."""
import pandas as pd
import pytest

from ddn import problems as P
from ddn.identity import build_examples
from ddn.load import load
from ddn.quality import check_alarms, check_timeseries, check_torque


@pytest.fixture(scope="module")
def data():
    P.DATA = P._Data()
    return P.DATA


def test_outage_and_stuck_sensor_found():
    issues = {i.check: i for i in check_timeseries(load("timeseries_1min.csv.gz"))}
    assert issues["Historian outage (all tags missing)"].count == 45
    assert "DDN1_PNT_ED_T301_TEMP.PV" in issues["Stuck (flat-lined) sensor"].evidence[0]


def test_alarm_duplicates_detected_despite_unique_ids():
    dup = [i for i in check_alarms(load("alarms_andon_events.csv")) if i.check.startswith("Duplicate")][0]
    assert dup.count > 200


def test_escaped_nok_torques():
    no_rehit = [i for i in check_torque(load("torque_results.csv.gz")) if "no re-hit" in i.check][0]
    assert no_rehit.count == 38   # 38 joints on 37 VINs


def test_weld_drift_window(data):
    s, e, _ = P.window_of("DDN1_BIW_L2_R07_WELDCUR.PV", lambda x: (x > 3) & (x < 9.5))
    assert s.date() == pd.Timestamp("2026-09-07").date() and e.date() == pd.Timestamp("2026-09-08").date()


def test_missed_rfid_reads_are_inferred(data):
    s, e = pd.Timestamp("2026-09-09 07:00"), pd.Timestamp("2026-09-09 09:00")
    read_only = P.vins_at("SLR-2", s, e)
    inferred = P.vins_at("SLR-2", s, e, infer_from=["SLR-1", "SLR-3"])
    assert len(inferred) > len(read_only) + 30   # reader RD-SLR-2 was offline


def test_identity_examples_resolve_relocated_robot():
    ex = build_examples()
    row = ex[ex["Functional location (SAP)"] == "`DDN1-BIW-L2-ST06-RB12`"].iloc[0]
    assert "L1ST3_RB5" in row["Historian tag(s)"]
