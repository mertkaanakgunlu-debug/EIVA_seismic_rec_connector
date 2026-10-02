"""Correction: a corrected COPY of the target, FFIDs from the authoritative reference, QC never in the way."""
import pytest

from shotlogfixer import engine_cli
from shotlogfixer.correction import CorrectionNotValidatedError
from shotlogfixer.qc import summarise

from helpers import INTERVAL, analysis_for, codes, reconcile, track, write_reference, write_target


def corrected_lines(analysis):
    return analysis.corrected_text.splitlines()


def association_by_ffid(analysis):
    return {row.reference.original_ffid: row for row in analysis.rows if row.reference}


# ---------------------------------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------------------------------

def test_case2_extra_target_row_is_target_only_and_removed(tmp_path):
    reference = [(501, 1000.0, 2000.0), (502, 1003.1, 2000.0), (503, 1006.3, 2000.0)]
    target = [(1, 1000.1, 2000.0), (2, 1001.6, 2030.0), (3, 1003.2, 2000.0), (4, 1006.4, 2000.0)]
    _, tgt, analysis = reconcile(tmp_path, reference, target)
    assert analysis.plan.safe_to_build and analysis.validation.passed
    assert (analysis.plan.assigned, analysis.plan.target_only_removed) == (3, 1)
    assert corrected_lines(analysis) == ["FFID,E(Spark),N(Spark),DATE,NOTE",
                                         "501,1000.10,2000.00,2025-01-01,row0",
                                         "502,1003.20,2000.00,2025-01-01,row2",
                                         "503,1006.40,2000.00,2025-01-01,row3"]
    only = [row for row in analysis.rows if row.association == "TARGET_ONLY"]
    assert [row.target.original_ffid for row in only] == ["2"]
    output = analysis.save_corrected(tmp_path / "fixed.txt")
    assert output.read_bytes() == analysis.corrected_text.encode("utf-8")


def test_case3_ffid_offset_follows_recorder_coordinates_and_order(tmp_path):
    _, _, analysis = reconcile(tmp_path, track(5, first_ffid=11), track(5, first_ffid=1))
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == ["11", "12", "13", "14", "15"]
    assert analysis.validation.checks["ffids_from_reference"] and analysis.validation.ffid_changed == 5


def test_case4_recorder_coordinate_anomaly_never_discards_the_record(tmp_path):
    reference = track(6, first_ffid=600)
    reference[3] = (603, reference[3][1] + 200.0, reference[3][2] + 60.0)     # one coordinate jumps ~209 m
    _, _, analysis = reconcile(tmp_path, reference, track(6, first_ffid=1))
    rows = association_by_ffid(analysis)
    anomalous = rows["603"]
    assert anomalous.association == "ASSIGNED" and anomalous.corrected_ffid == "603"
    assert anomalous.target.original_ffid == "4", "the sequence-consistent target row"
    assert anomalous.pair.basis == "SEQUENCE" and anomalous.pair.distance_m > 200
    assert anomalous.qc_severity == "SEVERE"
    assert {"RECORDER_POSITION_SPIKE", "ASSOCIATION_DISTANCE_SEVERE", "ASSOCIATION_SEQUENCE_ONLY"} <= {f.code for f in anomalous.findings}
    assert analysis.plan.safe_to_build and analysis.plan.assigned == 6
    assert "603" in analysis.corrected_text


def test_case4_terminal_jump_with_spare_trailing_rows_like_the_real_sample(tmp_path):
    reference = track(5, first_ffid=700)
    reference[4] = (704, reference[4][1] + 150.0, reference[4][2] + 120.0)    # last record jumps ~192 m
    target = track(6, first_ffid=1)                                           # one extra row after the line
    _, _, analysis = reconcile(tmp_path, reference, target)
    rows = association_by_ffid(analysis)
    assert rows["704"].association == "ASSIGNED" and rows["704"].target.original_ffid == "5"
    assert rows["704"].qc_severity == "SEVERE"
    assert (analysis.plan.assigned, analysis.plan.target_only_removed) == (5, 1)
    assert corrected_lines(analysis)[-1].startswith("704,")


def test_case7_large_distance_without_any_hard_rejection(tmp_path):
    reference = track(4, first_ffid=10)
    reference[1] = (11, reference[1][1] + 5000.0, reference[1][2] - 5000.0)
    _, _, analysis = reconcile(tmp_path, reference, track(4, first_ffid=1))
    assert analysis.plan.assigned == 4 and analysis.plan.safe_to_build
    assert association_by_ffid(analysis)["11"].association == "ASSIGNED"


def test_row_count_property_when_every_reference_record_is_assigned(tmp_path):
    _, _, analysis = reconcile(tmp_path, track(8, first_ffid=1), track(11, first_ffid=1))
    assert analysis.plan.assigned == analysis.plan.expected_rows == 8
    assert analysis.validation.corrected_rows == 8 and analysis.validation.checks["row_count"]
    assert analysis.validation.checks["every_valid_reference_record_accounted_for"] and analysis.plan.reference_without_target == 0
    assert len(corrected_lines(analysis)) == 1 + 8


def test_ffids_come_from_the_reference_never_from_the_target(tmp_path):
    reference = [(9001, 1000.0, 2000.0), (9002, 1003.1, 2000.0)]
    target = [(9002, 1000.1, 2000.0), (9001, 1003.2, 2000.0)]            # target FFIDs are swapped / wrong
    _, _, analysis = reconcile(tmp_path, reference, target)
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == ["9001", "9002"]


# ---------------------------------------------------------------------------------------------------
# QC warnings never block; only structural impossibilities do
# ---------------------------------------------------------------------------------------------------

def test_qc_warnings_do_not_block_a_corrected_copy(tmp_path):
    reference = [(100, 0.0, 0.0), (101, 3.1, 0.0), (102, 6.2, 0.0), (110, 500.0, 0.0), (111, 12.4, 0.0), (112, 15.5, 0.0)]
    _, _, analysis = reconcile(tmp_path, reference, track(6, first_ffid=1, x0=0.0, y0=0.0))
    severities = summarise(analysis.findings)["by_severity"]
    assert severities.get("SEVERE") and severities.get("WARNING")
    assert analysis.plan.blockers == [] and analysis.plan.safe_to_build and analysis.validation.passed
    assert analysis.plan.assigned == 6


def test_blocker_when_the_target_has_fewer_rows_than_valid_reference_records(tmp_path):
    ref, tgt, analysis = reconcile(tmp_path, track(5), track(4))
    assert [b.code for b in analysis.plan.blockers] == ["INSUFFICIENT_TARGET_ROWS"]
    assert not analysis.plan.safe_to_build and analysis.corrected_text is None and not analysis.validation.passed
    assert any(row.association == "BLOCKED" for row in analysis.rows)
    assert codes(analysis.findings, "ASSOCIATION_BLOCKED")
    with pytest.raises(CorrectionNotValidatedError):
        analysis.save_corrected(tmp_path / "never.txt")
    assert not (tmp_path / "never.txt").exists()
    response = engine_cli.analyse({"reference_path": str(ref), "target_path": str(tgt), "shot_interval_m": 3.125})
    assert response["ok"] and response["correction"]["safe"] is False
    assert response["correction"]["blockers"][0]["code"] == "INSUFFICIENT_TARGET_ROWS"


def test_blocker_for_reference_rows_that_cannot_be_interpreted(tmp_path):
    reference = tmp_path / "recorder.txt"
    reference.write_text("FFID SOU_X SOU_Y\n100 1000 2000\n101 1003 2000\n102 oops 2000\n103 1009 2000\n104 1012 2000\n")
    target = write_target(tmp_path, track(5, x0=1000.0, y0=2000.0, step=3.0))
    analysis = analysis_for(reference, target)
    assert [b.code for b in analysis.plan.blockers] == ["REFERENCE_ROWS_INVALID"]
    assert "line 4" in analysis.plan.blockers[0].message
    assert analysis.corrected_text is None
    assert any(row.association == "INVALID" for row in analysis.rows) and codes(analysis.findings, "RECORDER_INVALID_ROW")


def test_no_shot_rows_are_not_shots_and_do_not_block(tmp_path):
    reference = [(100, 0.0, 0.0), (101, 3.125, 0.0), (102, "-214748.36480", "-214748.36480"), (103, 9.375, 0.0)]
    target = track(4, first_ffid=1, x0=0.0, y0=0.0)
    _, _, analysis = reconcile(tmp_path, reference, target)
    assert analysis.plan.safe_to_build and analysis.plan.assigned == 3 and analysis.plan.expected_rows == 3
    assert [row.association for row in analysis.rows if row.association != "ASSIGNED"] == ["NO_SHOT", "TARGET_ONLY"]
    only = codes(analysis.findings, "TARGET_ONLY")[0]
    assert "no-shot" in only.message
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == ["100", "101", "103"]


def test_target_row_with_unusable_coordinates_keeps_its_place_in_the_sequence(tmp_path):
    target = tmp_path / "eiva.txt"
    rows = track(10, first_ffid=1, x0=1000.0, y0=2000.0)
    lines = [f"{f},{x:.2f},{y:.2f},d,n{i}" for i, (f, x, y) in enumerate(rows)]
    lines[4] = "5,garbage,2000.00,d,n4"
    target.write_text("FFID,E(Spark),N(Spark),DATE,NOTE\n" + "\n".join(lines) + "\n")
    reference = write_reference(tmp_path, track(10, first_ffid=300, x0=1000.0, y0=2000.0))
    analysis = analysis_for(reference, target)
    assert analysis.plan.safe_to_build and analysis.plan.assigned == 10
    row = [r for r in analysis.rows if r.target.original_ffid == "5"][0]
    assert row.association == "ASSIGNED" and row.corrected_ffid == "304" and row.pair.basis == "SEQUENCE"
    assert {"TARGET_INVALID_ROW", "ASSOCIATION_SEQUENCE_ONLY"} <= {f.code for f in row.findings}
    assert "304,garbage,2000.00,d,n4" in corrected_lines(analysis)


def test_unassigned_unreadable_target_row_is_removed_and_reported(tmp_path):
    target = tmp_path / "eiva.txt"
    rows = track(10, first_ffid=1, x0=1000.0, y0=2000.0)
    target.write_text("FFID,E(Spark),N(Spark),DATE,NOTE\n" + "".join(f"{f},{x:.2f},{y:.2f},d,n\n" for f, x, y in rows) + "999,oops,1,d,n\n")
    reference = write_reference(tmp_path, track(10, first_ffid=300, x0=1000.0, y0=2000.0))
    analysis = analysis_for(reference, target)
    assert analysis.plan.safe_to_build and (analysis.plan.assigned, analysis.plan.invalid_target_removed) == (10, 1)
    assert analysis.rows[-1].association == "INVALID"
    assert "removed" in codes(analysis.findings, "TARGET_INVALID_ROW")[0].message
    assert "999" not in analysis.corrected_text


# ---------------------------------------------------------------------------------------------------
# The corrected copy changes the FFID and nothing else
# ---------------------------------------------------------------------------------------------------

def test_only_the_ffid_field_changes_and_coordinates_are_not_reformatted(tmp_path):
    target = tmp_path / "eiva.txt"
    target.write_text("FFID,E(Spark),N(Spark),DATE,NOTE\n"
                      "  1,1000.1,2000,2025-01-01,   spaced   \n"
                      "  2,1003.256,2000.0,2025-01-02,\"quoted, with comma\"\n", encoding="utf-8")
    reference = write_reference(tmp_path, [(501, 1000.0, 2000.0), (502, 1003.2, 2000.0)])
    analysis = analysis_for(reference, target)
    assert corrected_lines(analysis)[1:] == ["  501,1000.1,2000,2025-01-01,   spaced   ",
                                            '  502,1003.256,2000.0,2025-01-02,"quoted, with comma"']
    assert analysis.validation.checks["unrelated_fields_unchanged"]


def test_bom_crlf_encoding_header_and_comments_are_preserved(tmp_path):
    target = tmp_path / "eiva.txt"
    raw = ("# survey line 7\r\n\r\nFFID,E(Spark),N(Spark),NOTE\r\n"
           "1,1000.1,2000,\"a, b\"\r\n2,1003.2,2000,plain\r\n3,1006.3,2000,x").encode("utf-8-sig")
    target.write_bytes(raw)
    reference = write_reference(tmp_path, [(501, 1000.0, 2000.0), (503, 1006.3, 2000.0)])
    analysis = analysis_for(reference, target)
    assert analysis.target_encoding == "utf-8-sig"
    output = analysis.save_corrected(tmp_path / "fixed.txt")
    data = output.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig") == ("# survey line 7\r\n\r\nFFID,E(Spark),N(Spark),NOTE\r\n"
                                        "501,1000.1,2000,\"a, b\"\r\n503,1006.3,2000,x")
    assert "\n" not in data.decode("utf-8-sig").replace("\r\n", "")


def test_whitespace_delimited_target_is_corrected_in_place(tmp_path):
    target = tmp_path / "nav.txt"
    target.write_text("FFID Easting Northing Depth\n1  1000.00 2000.00 5.5\n2  1003.10 2000.00 5.6\n9  1006.20 2000.00 5.7\n")
    reference = write_reference(tmp_path, [(101, 1000.0, 2000.0), (102, 1006.2, 2000.0)])
    analysis = analysis_for(reference, target)
    assert analysis.target_profile.structure.delimiter == "whitespace"
    assert corrected_lines(analysis) == ["FFID Easting Northing Depth", "101  1000.00 2000.00 5.5", "102  1006.20 2000.00 5.7"]


# ---------------------------------------------------------------------------------------------------
# Sources are never modified; guarded writes
# ---------------------------------------------------------------------------------------------------

def test_source_files_are_never_modified(tmp_path):
    ref, tgt, analysis = reconcile(tmp_path, track(5), track(7, first_ffid=1))
    before = (ref.read_bytes(), tgt.read_bytes(), ref.stat().st_mtime_ns, tgt.stat().st_mtime_ns)
    output = analysis.save_corrected(tmp_path / "fixed.txt")
    assert (ref.read_bytes(), tgt.read_bytes(), ref.stat().st_mtime_ns, tgt.stat().st_mtime_ns) == before
    assert output.exists() and not list(tmp_path.glob(".*.tmp"))


def test_output_path_guard_and_explicit_overwrite(tmp_path):
    ref, tgt, analysis = reconcile(tmp_path, track(3), track(3, first_ffid=1))
    for forbidden in (tgt, ref):
        with pytest.raises(ValueError):
            analysis.save_corrected(forbidden, overwrite=True)
    output = tmp_path / "fixed.txt"
    analysis.save_corrected(output)
    with pytest.raises(FileExistsError):
        analysis.save_corrected(output)
    output.write_text("old")
    analysis.save_corrected(output, overwrite=True)
    assert output.read_bytes() == analysis.corrected_text.encode("utf-8")
    assert not list(tmp_path.glob(".*.tmp"))


def test_changed_input_after_analysis_is_refused(tmp_path):
    ref, tgt, analysis = reconcile(tmp_path, track(3), track(3, first_ffid=1))
    tgt.write_text(tgt.read_text() + "4,9,9,d,n\n")
    with pytest.raises(CorrectionNotValidatedError):
        analysis.save_corrected(tmp_path / "fixed.txt")
    assert not (tmp_path / "fixed.txt").exists()


def test_engine_save_refuses_when_inputs_changed_since_analysis(tmp_path):
    ref, tgt, analysis = reconcile(tmp_path, track(3), track(3, first_ffid=1))
    payload = {"reference_path": str(ref), "target_path": str(tgt), "shot_interval_m": 3.125,
               "output_path": str(tmp_path / "fixed.txt"), "expected_hashes": analysis.input_hashes}
    ok = engine_cli.dispatch({**payload, "action": "save_corrected_target"})
    assert ok["ok"] and ok["rows"] == 3 and ok["raw_hashes_after"] == analysis.input_hashes
    tgt.write_text(tgt.read_text() + "4,9,9,d,n\n")
    bad = engine_cli.dispatch({**payload, "action": "save_corrected_target", "overwrite": True})
    assert bad["ok"] is False and bad["error"]["code"] == "INPUT_CHANGED"


def test_qc_cannot_change_the_correction(tmp_path):
    """The shot interval only sets QC bands; with a forced (one-to-one) sequence the corrected copy is identical."""
    reference = track(8, first_ffid=1)
    reference[4] = (5, reference[4][1] + 90.0, reference[4][2])
    texts = set()
    for interval in (0.5, INTERVAL, 12.5, 400.0):
        tmp = tmp_path / str(interval)
        tmp.mkdir()
        _, _, analysis = reconcile(tmp, reference, track(8, first_ffid=50), interval=interval)
        texts.add(analysis.corrected_text)
        assert analysis.plan.assigned == 8
    assert len(texts) == 1


# ---------------------------------------------------------------------------------------------------
# Spatial proximity first: structural discrepancies between the logs (exposed by the real OS_A-2 survey)
# ---------------------------------------------------------------------------------------------------

def test_recorder_positions_that_lead_the_target_by_one_shot_follow_the_positions(tmp_path):
    # Each recorder record carries the position of the NEXT target row, and the last record (no next fix) sits far away.
    n = 60
    target = [(1 + j, 1000.0 + INTERVAL * j, 2000.0) for j in range(n)]
    reference = [(500 + i, 1000.0 + INTERVAL * (i + 1), 2000.0) for i in range(n - 1)] + [(500 + n - 1, 1200.0, 2100.0)]
    _, _, analysis = reconcile(tmp_path, reference, target)
    assert analysis.plan.safe_to_build and analysis.validation.passed, "a record without a row never blocks the copy"
    assert (analysis.plan.assigned, analysis.plan.target_only_removed, analysis.plan.reference_without_target) == (59, 1, 1)
    assert not codes(analysis.findings, "ASSOCIATION_RUN_DISPLACED"), "no stretch of records was moved off its own position"
    rows = association_by_ffid(analysis)
    assert all(rows[str(500 + i)].target.row_index == i + 1 and rows[str(500 + i)].pair.distance_m < 1e-6 for i in range(n - 1))
    last = rows["559"]
    assert last.association == "BLOCKED" and last.target is None and last.corrected_ffid is None
    assert last.qc_severity == "SEVERE" and {"ASSOCIATION_BLOCKED", "RECORDER_POSITION_JUMP"} <= {f.code for f in last.findings}
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == [str(500 + i) for i in range(n - 1)]


def test_recorder_only_shot_is_reported_not_forced_onto_a_neighbour(tmp_path):
    shots = [(1000.0 + INTERVAL * k, 2000.0) for k in range(100)]
    reference = [(300 + k, x, y) for k, (x, y) in enumerate(shots)]                  # every shot was recorded
    target = shots[:40] + shots[41:80] + [shots[79]] + shots[80:]                     # shot 40 never logged; shot 79 logged twice
    target = [(1 + i, x, y) for i, (x, y) in enumerate(target)]
    _, _, analysis = reconcile(tmp_path, reference, target)
    assert analysis.plan.safe_to_build and analysis.validation.passed
    assert (analysis.plan.assigned, analysis.plan.reference_without_target, analysis.plan.target_only_removed) == (99, 1, 1)
    rows = association_by_ffid(analysis)
    assert rows["340"].association == "BLOCKED" and rows["340"].qc_severity == "SEVERE"
    (finding,) = codes(analysis.findings, "ASSOCIATION_BLOCKED")
    assert "recorder FFID 339" in finding.message and "next 39 recorder records" in finding.message
    # Every other shot sits on the target row at its own position; the logging gap did not shift the 39 shots after it.
    assert all(row.pair.distance_m < 1e-6 for ffid, row in rows.items() if ffid != "340")
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == [str(300 + k) for k in range(100) if k != 40]
    assert analysis.validation.checks["every_valid_reference_record_accounted_for"]


def test_recorder_outage_leaves_navigation_rows_unassigned_and_never_decides_identity_by_row_offset(tmp_path):
    """FFID 104 is followed by 105 after an outage while the navigation log kept running (about 100 rows between)."""
    positions = [(1000.0 + INTERVAL * k, 2000.0) for k in range(260)]
    shots = list(range(0, 5)) + list(range(106, 110)) + list(range(230, 235))         # target rows the recorder saw
    reference = [(100 + n, positions[k][0] + 0.1, positions[k][1]) for n, k in enumerate(shots)]
    target = [(9000 + k, x, y) for k, (x, y) in enumerate(positions)]                  # target FFIDs say nothing about identity
    _, _, analysis = reconcile(tmp_path, reference, target)
    assert analysis.plan.safe_to_build and analysis.plan.assigned == len(shots) and analysis.plan.reference_without_target == 0
    rows = association_by_ffid(analysis)
    assert [rows[str(100 + n)].target.row_index for n in range(len(shots))] == shots
    assert rows["105"].target.row_index - rows["104"].target.row_index == 102, "a jump of 102 rows is no penalty"
    assert analysis.plan.target_only_removed == 260 - len(shots)
    blocks = codes(analysis.findings, "TARGET_ONLY_BLOCK")
    assert [f.metrics["rows"] for f in blocks] == [101, 120, 25], "the unused stretches are reported by QC, not corrected differently"
    assert [line.split(",")[0] for line in corrected_lines(analysis)[1:]] == [str(100 + n) for n in range(len(shots))]
