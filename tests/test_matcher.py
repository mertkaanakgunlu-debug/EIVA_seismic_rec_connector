from shotlogfixer.matcher import match_records
from shotlogfixer.models import EivaRecord, RecorderRecord


def e(ffid, x):
    return EivaRecord(int(ffid), str(ffid), x, 0.0, [str(ffid), str(x), "0"])


def r(ffid, x, y=0.0, valid=True):
    return RecorderRecord(int(ffid), str(ffid), x, y, valid)


def statuses(results):
    return [(x.eiva_record.original_ffid if x.eiva_record else None, x.status) for x in results]


def test_perfect_alignment():
    out = match_records([e(i, i) for i in range(3)], [r(i, i) for i in range(3)])
    assert [x.status for x in out] == ["MATCHED"] * 3


def test_initial_eiva_only_rows_are_in_sequence():
    out = match_records([e(i, i) for i in range(5)], [r(1, 2), r(2, 3), r(3, 4)])
    assert statuses(out) == [("0", "EIVA_ONLY"), ("1", "EIVA_ONLY"), ("2", "MATCHED"), ("3", "MATCHED"), ("4", "MATCHED")]


def test_middle_missing_block_resynchronizes_without_anomaly():
    out = match_records([e(i, i) for i in range(7)], [r(1, 0), r(2, 1), r(3, 4), r(4, 5), r(5, 6)])
    assert [x.status for x in out] == ["MATCHED", "MATCHED", "EIVA_ONLY", "EIVA_ONLY", "MATCHED", "MATCHED", "MATCHED"]


def test_one_invalid_recorder_propagates_review_window():
    out = match_records([e(i, i) for i in range(5)], [r(1, 0), r(2, 0, 0, False), r(3, 4)])
    assert [x.status for x in out] == ["MATCHED", "RECORDER_INVALID", "REVIEW", "REVIEW", "REVIEW", "MATCHED"]


def test_multiple_invalid_recorder_rows_do_not_pick_one_eiva_row():
    out = match_records([e(i, i) for i in range(5)], [r(1, 0), r(2, 0, 0, False), r(3, 0, 0, False), r(4, 4)])
    assert [x.status for x in out] == ["MATCHED", "RECORDER_INVALID", "RECORDER_INVALID", "REVIEW", "REVIEW", "REVIEW", "MATCHED"]


def test_trailing_invalid_marks_remaining_rows_review():
    out = match_records([e(i, i) for i in range(4)], [r(1, 0), r(2, 0, 0, False)])
    assert [x.status for x in out] == ["MATCHED", "RECORDER_INVALID", "REVIEW", "REVIEW", "REVIEW"]


def test_no_candidate_enters_uncertainty_and_recovers():
    out = match_records([e(1, 0), e(2, 2), e(3, 3)], [r(1, 0), r(2, 100), r(3, 3)])
    assert [x.status for x in out] == ["MATCHED", "REVIEW", "REVIEW", "MATCHED"]


def test_ambiguous_coordinates_return_review():
    out = match_records([e(1, 0), e(2, 0.01)], [r(1, 0)])
    assert out[0].status == "REVIEW"
    assert [x.status for x in out[1:]] == ["REVIEW", "REVIEW"]


def test_small_difference_matches_and_outside_tolerance_does_not():
    assert match_records([e(1, 0.0)], [r(1, 0.03)])[0].status == "MATCHED"
    assert match_records([e(1, 0.0)], [r(1, 1.01)])[0].status == "REVIEW"


def test_ffid_discontinuity_is_not_special():
    out = match_records([e(541, 0), e(542, 1), e(543, 2), e(553, 3), e(554, 4)], [r(1, 2), r(2, 3), r(3, 4)])
    assert [(x.eiva_record.original_ffid, x.recorder_record.ffid) for x in out if x.status == "MATCHED"] == [("543", "1"), ("553", "2"), ("554", "3")]


def test_invalid_coordinate_variants_are_not_matched():
    for x, y in [(-214748.3648, -214748.3648), (-214748.3648, 1), (1, -214748.3648), (float("nan"), 1), (1, float("inf"))]:
        out = match_records([e(1, 0)], [r(1, x, y, False)])
        assert out[0].status == "RECORDER_INVALID"
