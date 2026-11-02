"""Day 8: anomaly detector logic on synthetic signals with known answers, judgement rules, and real results."""
import numpy as np
import pandas as pd
import pytest

from ddn import anomaly as A
from ddn import graph
from ddn.config import STAGING

IDX = pd.date_range("2026-09-01", "2026-09-05 23:59", freq="1min")       # Tue-Sat, no Sunday


def noisy(level=10.0, sd=0.1, seed=1):
    return pd.Series(level + np.random.default_rng(seed).normal(0, sd, len(IDX)), index=IDX)


def test_step_change_is_detected_with_its_window():
    s = noisy()
    s["2026-09-04 10:00":"2026-09-04 11:00"] -= 2.0               # 20 sd drop for an hour
    w = A.alarm_windows(A.robust_z(s))
    assert len(w) == 1 and w[0]["direction"] == "low"
    assert abs((w[0]["start"] - pd.Timestamp("2026-09-04 10:00")).total_seconds()) <= 15 * 60


def test_normal_noise_raises_no_alarm():
    assert A.alarm_windows(A.robust_z(noisy(seed=3))) == []


def test_hysteresis_merges_a_flickering_event_into_one():
    s = noisy()
    for h in range(10, 14):                                       # 4 bursts of 25 min, 5 min apart
        s[f"2026-09-04 {h}:00":f"2026-09-04 {h}:25"] += 3.0
        s[f"2026-09-04 {h}:25":f"2026-09-04 {h}:30"] += 1.0      # still above the low threshold
    assert len(A.alarm_windows(A.robust_z(s))) == 1


def test_judgement_rules():
    flat = {"detector": "flatline"}
    assert A.judge(flat, {}, {})[0] == "sensor_fault"
    ev = {"detector": "zscore_fast"}
    assert A.judge(ev, {"lift": 50, "defect_desc": "x", "defect_code": "X", "cases": 9}, {})[0] == "true_positive_quality"
    assert A.judge({**ev, "bake_ok": True}, {}, {})[0] == "false_alarm"
    assert A.judge(ev, {}, {"wo_number": "1", "wo_text": "bearing", "wo_failure_mode": "VIB"})[0] == "true_positive_equipment"
    assert A.judge(ev, {}, {})[0] == "false_alarm"


def test_oven_bake_window_rule():
    t0 = pd.Timestamp("2026-09-12 02:00")
    assert A.oven_within_bake_window(pd.Series([170.0, 177.0]), t0, t0 + pd.Timedelta("89min"))
    assert not A.oven_within_bake_window(pd.Series([185.0]), t0, t0 + pd.Timedelta("89min"))   # +35 C
    assert not A.oven_within_bake_window(pd.Series([170.0]), t0, t0 + pd.Timedelta("3h"))     # too long


@pytest.mark.skipif(not (STAGING / "anomalies.parquet").exists(), reason="run python -m ddn.anomaly first")
def test_all_signal_problems_found_and_judged():
    an = pd.read_parquet(STAGING / "anomalies.parquet")
    assert len(an) == 8
    assert an.judged.value_counts().to_dict() == {"true_positive_quality": 5, "true_positive_equipment": 1,
                                                  "sensor_fault": 1, "false_alarm": 1}
    oven = an[an.functional_location == "DDN1-PNT-OV2-Z3"].iloc[0]
    assert oven.judged == "false_alarm"


@pytest.mark.skipif(not graph.neo4j_available(wait_s=0), reason="Neo4j not running (docker compose up -d)")
def test_anomalies_in_graph():
    with graph.driver() as d, d.session() as s:
        n = s.run("MATCH (e:AnomalyEvent) RETURN count(e) AS n").single()["n"]
        caused = s.run("MATCH (:Defect)-[r:causedBy]->(:AnomalyEvent) RETURN count(r) AS n").single()["n"]
    assert n == 8 and caused > 100
