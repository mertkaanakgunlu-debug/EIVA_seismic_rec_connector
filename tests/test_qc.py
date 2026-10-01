from shotlogfixer.models import EivaRecord, MatchResult, RecorderRecord
from shotlogfixer.qc import (anomaly_event_count, ffid_discontinuities,
                             next_cycle, problem_result_indices)


def result(status, ffid):
    eiva = EivaRecord(int(ffid), str(ffid), float(ffid), 0.0, [], {})
    return MatchResult(eiva, None, None, status, "")


def test_adjacent_problem_rows_are_one_event():
    assert anomaly_event_count([result("EIVA_ONLY", 1), result("EIVA_ONLY", 2), result("MATCHED", 3)]) == 1


def test_separated_problem_regions_are_multiple_events():
    rows = [result("EIVA_ONLY", 1), result("MATCHED", 2), result("REVIEW", 3), result("MATCHED", 4)]
    assert anomaly_event_count(rows) == 2


def test_recorder_anomaly_and_review_region_group_together():
    rows = [result("MATCHED", 1), MatchResult(None, RecorderRecord(2, "2", 0, 0, False), None, "RECORDER_INVALID", ""), result("REVIEW", 3), result("MATCHED", 4)]
    assert anomaly_event_count(rows) == 1


def test_navigation_order_and_wrap():
    rows = [result("MATCHED", 1), result("REVIEW", 2), result("EIVA_ONLY", 3), result("REVIEW", 4)]
    indices = problem_result_indices(rows, "REVIEW")
    assert indices == [1, 3]
    assert next_cycle(indices, None, 1) == 1
    assert next_cycle(indices, 3, 1) == 1
    assert next_cycle(indices, 1, -1) == 3


def test_ffid_discontinuities_are_informational_only():
    records = [EivaRecord(i, ffid, float(i), 0, []) for i, ffid in enumerate(("541", "542", "543", "553", "554"))]
    assert ffid_discontinuities(records) == [("543", "553")]
    continuous = [EivaRecord(i, str(i), float(i), 0, []) for i in range(3)]
    assert ffid_discontinuities(continuous) == []


def test_header_value_mapping_keeps_raw_strings():
    record = EivaRecord(2, "102", 1.0, 2.0, ["102", "1.00"], {"FFID": "102", "E(Spark)": "1.00"})
    assert record.original_values_by_column["E(Spark)"] == "1.00"
