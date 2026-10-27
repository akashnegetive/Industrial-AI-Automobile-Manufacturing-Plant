"""Day 6: documents, work-order failure modes, stations/alarms, VIN traceability."""
import re

import numpy as np
import pandas as pd
import pytest

from ddn.context import mes_to_fl, normalise_source
from ddn.documents import LABEL_RULES, OCR_FIXES, normalise
from ddn.trace import fill_missing
from ddn.workorders import analyse, build_nlp


@pytest.mark.parametrize("code,fl", [
    ("B2-04", "DDN1-BIW-L2-ST04"), ("SLR-2", "DDN1-PNT-SL-ST02"), ("TC-2", "DDN1-PNT-TC2"),
    ("F1-03", "DDN1-ASM-FN1-ST03"), ("EOL-WT", "DDN1-ASM-EOL-WT"), ("BIQ-1", "DDN1-BIW-QI-ST01"),
])
def test_mes_station_to_fl(code, fl):
    assert mes_to_fl(code) == fl


@pytest.mark.parametrize("src", ["BIW/L2/S4/RB07", "BIW.L2.ST04.RB07", "BIW_L2_ST04_RB07"])
def test_alarm_source_separators(src):
    assert normalise_source(src) == "DDN1-BIW-L2-ST04-RB07"


def _keys(text):
    return {fn(m, "L2")[1] for pat, fn in LABEL_RULES for m in re.finditer(pat, normalise(text))}


def test_drawing_labels():
    assert {"RB07", "RB07WG", "ST04TD"} <= _keys("RB-207 GUN WG-207 TD-2.04")
    assert ("Z3", "TEMP") in _keys("TE 423 BNR-B3") and "Z3BR" in _keys("TE 423 BNR-B3")


def test_ocr_corrections_only_inside_label_shapes():
    fixed = "LUB-12 OLF-7 4 QLP-1.3 plain text"
    for pat, rep in OCR_FIXES:
        fixed = re.sub(pat, rep, fixed)
    assert "LUB-1.2" in fixed and "OLP-1.4" in fixed and "OLP-1.3" in fixed and "plain text" in fixed


def test_failure_modes_including_hinglish():
    wos = pd.DataFrame({"wo_number": ["1", "2", "3", "4"], "wo_type": ["CM", "CM", "CAL", "PM"],
                        "short_text": ["pump P102 trip ho raha hai, overload reset", "Sealer robo 3 nozzle not heating",
                                       "NR14 transducer calibration - found offset", "R7 6-monthly PM: grease axes"],
                        "long_text": [None] * 4, "failure_code": [None] * 4})
    r = analyse(build_nlp(), wos).set_index("wo_number")
    assert r.iso14224[["1", "2", "3"]].tolist() == ["UST", "LOO", "PDE"] and pd.isna(r.iso14224["4"])
    assert r.activity["4"] == "routine"


def test_missing_read_is_interpolated_from_the_cars_own_delay():
    offsets = pd.Series([0.0, 10.0, 20.0], index=["A", "B", "C"])
    M = pd.DataFrame([[3.0, np.nan, 25.0]], columns=["A", "B", "C"])     # 3 min late at A, 5 min late at C
    assert fill_missing(M, offsets).loc[0, "B"] == pytest.approx(14.0)   # -> ~4 min late at B
