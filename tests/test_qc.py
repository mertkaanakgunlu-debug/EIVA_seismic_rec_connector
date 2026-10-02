"""QC findings: reported independently of the correction, never able to change it."""
import copy
import math

from shotlogfixer.alignment import Association, AlignmentResult, align_records
from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.models import INFO, REFERENCE, SEVERE, TARGET, WARNING
from shotlogfixer.qc import association_confidence, distance_band, run_qc, summarise, worst_severity

from helpers import PARAMS, codes, qc_for, rec, target_records

STEP = 3.125


def line_ref(xs, ffids=None):
    ffids = ffids or [100 + i for i in range(len(xs))]
    return [rec(REFERENCE, i, x, 0.0, f) for i, (x, f) in enumerate(zip(xs, ffids))]


def line_tgt(xs):
    return target_records([(x, 0.0) for x in xs])


# ---------------------------------------------------------------------------------------------------
# Recorder QC
# ---------------------------------------------------------------------------------------------------

def test_recorder_ffid_gaps_reversals_and_duplicates():
    xs = [STEP * i for i in range(7)]
    _, findings = qc_for(line_ref(xs, [1, 2, 4, 5, 5, 3, 7]), line_tgt(xs))
    disc = codes(findings, "RECORDER_FFID_DISCONTINUITY")
    assert [(f.metrics["from"], f.metrics["to"], f.metrics["kind"], f.severity) for f in disc] == [
        (2, 4, "GAP", INFO), (5, 3, "REVERSAL", WARNING), (3, 7, "GAP", WARNING)]
    assert [(f.metrics["ffid"], f.reference_row) for f in codes(findings, "RECORDER_DUPLICATE_FFID")] == [(5, 4)]


def test_target_ffid_oddities_are_informational_only():
    xs = [STEP * i for i in range(5)]
    tgt = target_records([(x, 0.0) for x in xs], first_ffid=1)
    tgt = [rec(TARGET, t.row_index, t.x, t.y, f) for t, f in zip(tgt, [1, 2, 2, 9, 10])]
    _, findings = qc_for(line_ref(xs), tgt)
    mine = [f for f in findings if f.code.startswith("TARGET_") and "FFID" in f.code]
    assert {f.code for f in mine} == {"TARGET_DUPLICATE_FFID", "TARGET_FFID_DISCONTINUITY"}
    assert all(f.severity == INFO for f in mine)
    assert any("diagnostics only" in f.message for f in mine)


def test_position_jump_threshold_is_inclusive_and_severity_grows_at_twenty_intervals():
    params = AnalysisParameters(5.0)                          # jump at 25 m, severe at 100 m
    for step, expected in ((24.99, None), (25.0, WARNING), (99.9, WARNING), (100.0, SEVERE)):
        xs = [0.0, 5.0, 5.0 + step, 10.0 + step]
        _, findings = qc_for(line_ref(xs), line_tgt(xs), params)
        jumps = codes(findings, "RECORDER_POSITION_JUMP")
        if expected is None:
            assert not jumps and codes(findings, "RECORDER_SPACING_IRREGULAR"), "just below the threshold is only irregular spacing"
        else:
            assert [f.severity for f in jumps] == [expected] and jumps[0].reference_row == 2


def test_isolated_position_spike_is_one_finding_not_two_jumps():
    xs = [0.0, STEP, 2 * STEP, 400.0, 4 * STEP, 5 * STEP]
    _, findings = qc_for(line_ref(xs), line_tgt([STEP * i for i in range(6)]))
    spikes = codes(findings, "RECORDER_POSITION_SPIKE")
    assert [(f.severity, f.reference_row) for f in spikes] == [(SEVERE, 3)]
    assert not codes(findings, "RECORDER_POSITION_JUMP")


def test_terminal_jump_is_reported_on_the_last_record():
    xs = [STEP * i for i in range(4)] + [500.0]
    _, findings = qc_for(line_ref(xs), line_tgt([STEP * i for i in range(5)]))
    (jump,) = codes(findings, "RECORDER_POSITION_JUMP")
    assert jump.severity == SEVERE and jump.reference_row == 4 and jump.metrics["intervals"] > 50


def test_duplicate_coordinates_and_irregular_spacing():
    xs = [0.0, STEP, STEP, 2 * STEP, 2 * STEP + 0.9, 2 * STEP + 0.9 + 8.0]
    _, findings = qc_for(line_ref(xs), line_tgt([STEP * i for i in range(6)]))
    assert [(f.severity, f.reference_row) for f in codes(findings, "RECORDER_DUPLICATE_COORDINATE")] == [(WARNING, 2)]
    assert [f.reference_row for f in codes(findings, "RECORDER_SPACING_IRREGULAR")] == [4, 5]
    # the same repetition in the target is only a note
    _, findings = qc_for(line_ref([STEP * i for i in range(3)]), line_tgt([0.0, STEP, STEP]))
    assert [f.severity for f in codes(findings, "TARGET_DUPLICATE_COORDINATE")] == [INFO]


def test_many_irregular_spacings_are_summarised_and_flag_a_wrong_shot_interval():
    xs = [8.0 * i for i in range(250)]
    _, findings = qc_for(line_ref(xs), line_tgt(xs))
    (summary,) = codes(findings, "RECORDER_SPACING_IRREGULAR", "RECORDER")
    assert summary.severity == WARNING and summary.metrics["count"] == 249
    (mismatch,) = codes(findings, "SHOT_INTERVAL_MISMATCH")
    assert mismatch.metrics["median_spacing_m"] == 8.0


def test_shot_interval_mismatch_depends_on_the_entered_interval():
    xs = [3.1 * i for i in range(30)]
    assert not codes(qc_for(line_ref(xs), line_tgt(xs))[1], "SHOT_INTERVAL_MISMATCH")
    assert codes(qc_for(line_ref(xs), line_tgt(xs), AnalysisParameters(12.5))[1], "SHOT_INTERVAL_MISMATCH")


def test_invalid_and_no_shot_reference_rows_are_reported():
    ref = [rec(REFERENCE, 0, 0.0, 0.0, 1), rec(REFERENCE, 1, None, None, 2, "INVALID", "coordinate is missing"),
           rec(REFERENCE, 2, 1.0, 1.0, 3, "NO_SHOT", "sentinel"), rec(REFERENCE, 3, STEP, 0.0, 4)]
    _, findings = qc_for(ref, line_tgt([0.0, STEP, 2 * STEP]))
    assert [(f.severity, f.reference_row) for f in codes(findings, "RECORDER_INVALID_ROW")] == [(WARNING, 1)]
    assert [(f.severity, f.reference_row) for f in codes(findings, "RECORDER_NO_SHOT_ROW")] == [(INFO, 2)]


# ---------------------------------------------------------------------------------------------------
# Target QC
# ---------------------------------------------------------------------------------------------------

def test_target_only_rows_blocks_and_context():
    ref = line_ref([0.0, STEP, 2 * STEP], [501, 502, 503])
    tgt = line_tgt([0.0, STEP, 2 * STEP, 100.0, 110.0, 120.0, 130.0, 140.0])
    alignment, findings = qc_for(ref, tgt)
    only = codes(findings, "TARGET_ONLY")
    assert [f.target_row for f in only] == [3, 4, 5, 6, 7] and all(f.severity == INFO for f in only)
    assert "recorder FFID 503" in only[0].message and "end of the recorder log" in only[0].message
    (block,) = codes(findings, "TARGET_ONLY_BLOCK")
    assert block.severity == WARNING and block.metrics["rows"] == 5 and block.target_row == 3
    assert alignment.complete


def test_unreadable_target_rows_are_reported_in_both_outcomes():
    tgt = target_records([(0.0, 0.0), (None, None), (2 * STEP, 0.0)])
    _, findings = qc_for(line_ref([0.0, STEP, 2 * STEP]), tgt)           # assigned by sequence continuity
    (assigned,) = codes(findings, "TARGET_INVALID_ROW")
    assert "assigned by sequence continuity" in assigned.message and assigned.severity == WARNING
    tgt = target_records([(0.0, 0.0), (STEP, 0.0), (None, None)])        # left over: removed
    _, findings = qc_for(line_ref([0.0, STEP]), tgt)
    (removed,) = codes(findings, "TARGET_INVALID_ROW")
    assert "removed" in removed.message
    assert not codes(findings, "TARGET_ONLY"), "an unreadable leftover row is reported once, as invalid"


def test_target_position_jumps_are_unusual_sequence_behaviour():
    xs = [STEP * i for i in range(4)] + [500.0]
    _, findings = qc_for(line_ref([STEP * i for i in range(5)]), line_tgt(xs))
    (jump,) = codes(findings, "TARGET_POSITION_JUMP")
    assert jump.severity == SEVERE and jump.target_row == 4


# ---------------------------------------------------------------------------------------------------
# Association QC
# ---------------------------------------------------------------------------------------------------

def test_distance_bands_confidence_and_sequence_only():
    ref = [rec(REFERENCE, i, 100.0 * i, 0.0, 100 + i) for i in range(4)]
    offsets = [1.0, 2.0, 8.0, 40.0]
    tgt = target_records([(100.0 * i, off) for i, off in enumerate(offsets)])
    alignment, findings = qc_for(ref, tgt)
    assoc = [f for f in findings if f.scope == "ASSOCIATION"]
    by_row = lambda code: [f.reference_row for f in assoc if f.code == code]
    assert by_row("ASSOCIATION_DISTANCE_ELEVATED") == [1] and by_row("ASSOCIATION_DISTANCE_LARGE") == [2]
    assert by_row("ASSOCIATION_DISTANCE_SEVERE") == [3] and by_row("ASSOCIATION_SEQUENCE_ONLY") == [3]
    assert [f.severity for f in assoc if f.code == "ASSOCIATION_DISTANCE_LARGE"] == [WARNING]
    assert [distance_band(a.distance_m, PARAMS) for a in alignment.associations] == ["NORMAL", "ELEVATED", "LARGE", "SEVERE"]
    assert [association_confidence(a, PARAMS) for a in alignment.associations] == ["HIGH", "MEDIUM", "LOW", "LOW"]


def test_competing_placements_are_flagged_ambiguous():
    _, findings = qc_for(line_ref([0.0]), line_tgt([0.0, 0.0]))
    (flag,) = codes(findings, "ASSOCIATION_AMBIGUOUS")
    assert flag.severity == WARNING and flag.metrics["alternative_target_rows"] == [1]


def test_forced_placements_are_never_ambiguous_even_when_points_look_alike():
    _, findings = qc_for(line_ref([0.0, 0.0]), line_tgt([0.0, 0.0]))
    assert not codes(findings, "ASSOCIATION_AMBIGUOUS")


def placed_by_hand(ref, tgt, mapping):
    """An alignment that puts reference row i on target row mapping[i]: QC must describe any alignment it is given."""
    result = AlignmentResult(reference_valid=len(ref), target_rows=len(tgt))
    for i, j in mapping.items():
        result.associations.append(Association(i, j, math.hypot(ref[i].x - tgt[j].x, ref[i].y - tgt[j].y), "SPATIAL", False))
    result.by_reference = {a.reference_row: a for a in result.associations}
    result.by_target = {a.target_row: a for a in result.associations}
    return result


def test_nearest_row_not_used_and_a_displaced_run():
    # A safety net for any alignment that leaves records one row off: every reference record sits on the target row
    # before the one at its own position.
    ref = line_ref([STEP * i for i in range(40)])
    tgt = line_tgt([STEP * (j - 1) + 0.05 for j in range(40)])
    findings = run_qc(ref, tgt, placed_by_hand(ref, tgt, {i: i for i in range(40)}), PARAMS)
    assert len(codes(findings, "ASSOCIATION_NEAREST_OVERRIDDEN")) == 39
    (run,) = codes(findings, "ASSOCIATION_RUN_DISPLACED")
    assert run.severity == WARNING and run.metrics["records"] == 39 and "one place before" in run.message
    assert run.metrics["median_nearest_distance_m"] < 0.1 < run.metrics["median_assigned_distance_m"]


def test_the_aligner_follows_positions_so_the_same_offset_logs_raise_no_displaced_run():
    ref = line_ref([STEP * i for i in range(40)])
    tgt = line_tgt([STEP * (j - 1) + 0.05 for j in range(40)])
    alignment, findings = qc_for(ref, tgt)
    assert not codes(findings, "ASSOCIATION_RUN_DISPLACED") and not codes(findings, "ASSOCIATION_NEAREST_OVERRIDDEN")
    assert [a.target_row for a in alignment.associations] == list(range(1, 40))
    (blocked,) = codes(findings, "ASSOCIATION_BLOCKED")
    assert blocked.reference_row == 39, "the last record has no target row beyond the end of the log"


def test_unplaceable_reference_records_are_severe_blocked_findings():
    xs = [STEP * i for i in range(4)]
    alignment, findings = qc_for(line_ref(xs), line_tgt(xs[:3]))
    assert not alignment.complete
    (blocked,) = codes(findings, "ASSOCIATION_BLOCKED")
    assert blocked.severity == SEVERE and blocked.reference_row == alignment.unplaced_reference_rows[0]
    assert "the target has 3 rows but the recorder has 4 valid records" in blocked.message


def test_unplaced_record_names_its_rival_and_prices_making_room():
    xs = [STEP * i for i in range(60)]
    reference = line_ref(xs[:11] + [xs[10] + 0.3] + xs[11:])        # the shot at xs[10] is recorded twice
    target = line_tgt(xs[:40] + [xs[39] + 0.5] + xs[40:])           # the target has one row there and a spare one later
    alignment, findings = qc_for(reference, target)
    assert alignment.unplaced_reference_rows == [11]
    (blocked,) = codes(findings, "ASSOCIATION_BLOCKED")
    assert blocked.severity == SEVERE and blocked.reference_row == 11
    assert "belongs to recorder FFID 110 (it fits it better, 0.00 m)" in blocked.message
    assert "no free target row lies between recorder FFID 110 and FFID 112" in blocked.message
    assert "next 29 recorder records one target row later (to the unused row at line 41)" in blocked.message
    assert blocked.metrics["shift_records"] == 29 and blocked.metrics["shift_cost_m"] > 80


def test_unplaced_terminal_record_explains_that_no_target_row_is_left():
    xs = [STEP * i for i in range(50)]
    reference = line_ref(xs + [500.0])                              # the last record's coordinate jumps
    target = line_tgt(xs[:20] + [xs[19] + 0.5] + xs[20:])
    _, findings = qc_for(reference, target)
    (blocked,) = codes(findings, "ASSOCIATION_BLOCKED")
    assert "no target row lies within 15.625 m of its coordinate and no free target row lies after recorder FFID 149" in blocked.message
    assert "previous 30 recorder records one target row earlier" in blocked.message
    assert [f.code for f in findings if f.reference_row == 50 and f.scope == "RECORDER"] == ["RECORDER_POSITION_JUMP"]


# ---------------------------------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------------------------------

def test_running_qc_does_not_touch_the_alignment():
    ref = line_ref([STEP * i for i in range(10)])
    ref[4] = rec(REFERENCE, 4, 900.0, 0.0, 104)
    tgt = line_tgt([STEP * i for i in range(12)])
    alignment = align_records(ref, tgt, PARAMS)
    snapshot = copy.deepcopy(alignment)
    findings = run_qc(ref, tgt, alignment, PARAMS)
    assert alignment == snapshot and findings
    assert worst_severity(findings) == SEVERE and worst_severity([]) is None
    summary = summarise(findings)
    assert summary["total"] == len(findings) and sum(summary["by_severity"].values()) == len(findings)
