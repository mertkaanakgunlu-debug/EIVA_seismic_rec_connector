"""Integration regression on a real survey pair (OS_A-2 recorder pronav log + EIVA log).

Real acquisition data is not committed to the repository.  The test looks for the files in
``SHOTLOGFIXER_REAL_DIR`` (default: ``~/Downloads``) and skips when they are not present:

    OS_A-2_pronav.txt  (or OS_A-2_pronav(1).txt)   recorder / reference log, headerless ``FFID,X,Y``
    OS_A-2_LOG.txt                                  EIVA / target log with a header

The counts below belong to this specific sample: 6,769 EIVA rows, 6,764 recorder records, FFID 101..6873, and a ~210 m
recorder position jump in the last record (FFID 6873).  Spatially the two logs disagree in two places that no
order-preserving one-to-one assignment can reconcile without moving hundreds of records onto a worse row:

* FFID 2525 and 2526 were recorded 0.4 m apart where the EIVA log holds a single row;
* the last recorder record (FFID 6873) lies beyond the end of the EIVA log (that log's final row is FFID 6872's position).

Spatial proximity is the primary signal, so those two records are reported as having no EIVA row instead of shifting
236 and 1,216 correct associations by one row.
"""
import hashlib
import math
import os
import time
from pathlib import Path

import pytest

from shotlogfixer import engine_cli

DIRECTORY = Path(os.environ.get("SHOTLOGFIXER_REAL_DIR", Path.home() / "Downloads"))
REFERENCE = next((p for p in (DIRECTORY / "OS_A-2_pronav.txt", DIRECTORY / "OS_A-2_pronav(1).txt") if p.exists()), None)
TARGET = DIRECTORY / "OS_A-2_LOG.txt"

pytestmark = pytest.mark.skipif(REFERENCE is None or not TARGET.exists(),
                                reason="real OS_A-2 sample not available (set SHOTLOGFIXER_REAL_DIR)")

WITHOUT_ROW = ["2525", "6873"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    before = (sha(REFERENCE), sha(TARGET))
    payload = {"reference_path": str(REFERENCE), "target_path": str(TARGET), "shot_interval_m": 3.125}
    started = time.perf_counter()
    analysis, failure = engine_cli.prepare_analysis(payload)
    elapsed = time.perf_counter() - started
    assert failure is None, failure
    output = tmp_path_factory.mktemp("real") / "OS_A-2_LOG_corrected.txt"
    analysis.save_corrected(output)
    return analysis, output, before, elapsed


def by_ffid(analysis):
    return {row.reference.original_ffid: row for row in analysis.rows if row.reference}


def test_row_counts_and_authority(run):
    analysis, _, _, elapsed = run
    assert len(analysis.target) == 6769 and len(analysis.reference) == 6764
    assert analysis.alignment.reference_valid == 6764 and analysis.alignment.direction == "REFERENCE_TO_TARGET"
    assert analysis.plan.blockers == [] and analysis.validation.passed, "records without a row never block the corrected copy"
    assert elapsed < 60


def test_assignment_is_one_to_one_and_monotone(run):
    analysis, *_ = run
    pairs = analysis.alignment.associations
    assert len(pairs) == 6762
    assert [p.reference_row for p in pairs] == [r for r in range(6764) if analysis.reference[r].original_ffid not in WITHOUT_ROW]
    targets = [p.target_row for p in pairs]
    assert len(set(targets)) == len(targets) and all(a < b for a, b in zip(targets, targets[1:]))
    assert analysis.validation.checks["every_valid_reference_record_accounted_for"]


def test_every_recorder_record_is_assigned_or_reported_as_having_no_row(run):
    analysis, *_ = run
    records = [row for row in analysis.rows if row.reference]          # the recorder log repeats a few FFIDs, so count rows
    assert len(records) == 6764, "no recorder record disappears from the result"
    assert sorted(row.reference.original_ffid for row in records if row.association == "BLOCKED") == WITHOUT_ROW
    assert all(row.association == "ASSIGNED" for row in records if row.reference.original_ffid not in WITHOUT_ROW)
    assert analysis.plan.reference_without_target == 2


def test_corrected_copy_has_one_row_per_assigned_record_with_recorder_ffids(run):
    analysis, output, *_ = run
    lines = output.read_bytes().decode("utf-8").splitlines()
    assert lines[0].startswith("DATE,TIME,FFID,E(Spark)")
    data = lines[1:]
    assert len(data) == 6762 == analysis.plan.corrected_rows and analysis.plan.target_only_removed == 7
    assert [row.split(",")[2].strip() for row in data] == [r.original_ffid for r in analysis.reference if r.original_ffid not in WITHOUT_ROW]
    assert analysis.validation.checks["unrelated_fields_unchanged"] and analysis.validation.checks["structure_preserved"]


def test_unused_eiva_rows_are_excluded(run):
    analysis, output, *_ = run
    removed = [row.target for row in analysis.rows if row.association == "TARGET_ONLY"]
    assert len(removed) == 7
    kept_lines = output.read_bytes().decode("utf-8").splitlines()
    for t in removed:
        # a removed row's date/time stamp does not survive anywhere in the corrected copy
        assert not any(line.startswith(t.cells[0] + "," + t.cells[1] + ",") for line in kept_lines)
    assert [a.action for a in analysis.plan.actions].count("DROP_TARGET_ONLY") == 7


def test_source_files_are_unchanged(run):
    analysis, _, before, _ = run
    assert (sha(REFERENCE), sha(TARGET)) == before
    assert before == (analysis.input_hashes["reference"], analysis.input_hashes["target"])


def test_spatial_proximity_decides_not_a_preferred_row_lag(run):
    """No stretch of records is moved off its own position to keep a row for the two records the target cannot hold."""
    analysis, *_ = run
    target, reference = analysis.target, analysis.reference
    worse = []
    for a in analysis.alignment.associations:
        r = reference[a.reference_row]
        low, high = max(0, a.target_row - 12), min(len(target), a.target_row + 13)
        nearest = min(math.hypot(r.x - t.x, r.y - t.y) for t in target[low:high])
        worse.append(a.distance_m - nearest)
    assert max(a.distance_m for a in analysis.alignment.associations) < 3.125, "no record sits more than one shot interval from its row"
    assert sum(w > 1.0 for w in worse) <= 20 and max(worse) < 2.0, "the previous mandatory assignment put ~1,450 records one row off"
    assert sum(w for w in worse if w > 0.05) < 100, "...adding about 2.8 km of distance"
    assert not [f for f in analysis.findings if f.code == "ASSOCIATION_RUN_DISPLACED"]


def test_terminal_recorder_jump_is_qc_not_evidence_of_a_missing_shot(run):
    analysis, *_ = run
    rows = by_ffid(analysis)
    last = rows["6873"]
    assert last.association == "BLOCKED" and last.reference.x is not None, "the record stays in the result with its coordinates"
    assert last.qc_severity == "SEVERE" and {f.code for f in last.findings} == {"RECORDER_POSITION_JUMP", "ASSOCIATION_BLOCKED"}
    detail = analysis.alignment.unplaced[last.reference.row_index]
    assert detail.nearest_target_row is None and detail.shift_records > 1000 and detail.shift_side == "BEFORE"
    message = next(f.message for f in last.findings if f.code == "ASSOCIATION_BLOCKED")
    assert "no free target row lies after recorder FFID 6872" in message
    assert "does not exist" not in message and "unrecorded" not in message, "a missing EIVA row says nothing against the shot"
    last_two = [rows[f] for f in ("6871", "6872")]
    assert all(r.association == "ASSIGNED" and r.qc_severity != "SEVERE" for r in last_two)
    assert [r.target.row_index for r in last_two] == [len(analysis.target) - 2, len(analysis.target) - 1]


def test_doubly_recorded_shot_keeps_the_better_fitting_record(run):
    analysis, *_ = run
    rows = by_ffid(analysis)
    assert rows["2525"].association == "BLOCKED" and rows["2526"].association == "ASSIGNED"
    assert rows["2526"].target.source_line_number == 2428 and rows["2526"].pair.distance_m < 0.6
    message = next(f.message for f in rows["2525"].findings if f.code == "ASSOCIATION_BLOCKED")
    assert "belongs to recorder FFID 2526" in message and "next 236 recorder records" in message
