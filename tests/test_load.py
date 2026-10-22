"""Tests protect the typing rules in ddn.load from being broken later."""
from ddn.load import load


def test_equipment_numbers_are_text_without_decimal():
    wo = load("maintenance_work_orders.csv")
    nums = wo["equipment_no"].dropna()
    assert not nums.str.endswith(".0").any()


def test_timestamps_parsed():
    v = load("vehicles.csv")
    assert str(v["body_start_at"].dtype).startswith("datetime64")


def test_row_counts_match_data_dictionary():
    assert len(load("assets_cmms_export.csv")) == 455
    assert len(load("historian_tag_list.csv")) == 1541
