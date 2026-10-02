"""Integration regression on a real survey pair (OS_A-2 recorder pronav log + EIVA log).

Real acquisition data is not committed to the repository.  The test looks for the files in
``SHOTLOGFIXER_REAL_DIR`` (default: ``~/Downloads``) and skips when they are not present:

    OS_A-2_pronav.txt  (or OS_A-2_pronav(1).txt)   recorder / reference log, headerless ``FFID,X,Y``
    OS_A-2_LOG.txt                                  EIVA / target log with a header

The counts below belong to this specific sample: 6,769 EIVA rows, 6,764 recorder records, FFID 101..6873, a ~210 m
recorder position jump in the last record (FFID 6873), and EIVA rows that have no recorder counterpart.
"""
import hashlib
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


def test_row_counts_and_authority(run):
    analysis, _, _, elapsed = run
    assert len(analysis.target) == 6769 and len(analysis.reference) == 6764
    assert analysis.alignment.reference_valid == 6764 and analysis.alignment.complete
    assert analysis.alignment.direction == "REFERENCE_TO_TARGET"
    assert analysis.plan.blockers == [] and analysis.validation.passed
    assert elapsed < 60


def test_assignment_is_one_to_one_monotone_and_complete(run):
    analysis, *_ = run
    pairs = analysis.alignment.associations
    assert len(pairs) == 6764
    assert [p.reference_row for p in pairs] == list(range(6764))
    targets = [p.target_row for p in pairs]
    assert len(set(targets)) == len(targets) and all(a < b for a, b in zip(targets, targets[1:]))


def test_corrected_copy_has_one_row_per_recorder_record_with_recorder_ffids(run):
    analysis, output, *_ = run
    lines = output.read_bytes().decode("utf-8").splitlines()
    assert lines[0].startswith("DATE,TIME,FFID,E(Spark)")
    data = lines[1:]
    assert len(data) == 6764 and analysis.plan.target_only_removed == 5
    assert [row.split(",")[2].strip() for row in data] == [r.original_ffid for r in analysis.reference]
    assert analysis.validation.checks["unrelated_fields_unchanged"] and analysis.validation.checks["structure_preserved"]


def test_unused_eiva_rows_are_excluded(run):
    analysis, output, *_ = run
    removed = [row.target for row in analysis.rows if row.association == "TARGET_ONLY"]
    assert len(removed) == 5
    kept_lines = output.read_bytes().decode("utf-8").splitlines()
    for t in removed:
        # a removed row's date/time stamp does not survive anywhere in the corrected copy
        assert not any(line.startswith(t.cells[0] + "," + t.cells[1] + ",") for line in kept_lines)
    assert [a.action for a in analysis.plan.actions].count("DROP_TARGET_ONLY") == 5


def test_source_files_are_unchanged(run):
    analysis, _, before, _ = run
    assert (sha(REFERENCE), sha(TARGET)) == before
    assert before == (analysis.input_hashes["reference"], analysis.input_hashes["target"])


def test_terminal_recorder_jump_is_qc_not_evidence_of_a_missing_shot(run):
    analysis, *_ = run
    by_ffid = {row.reference.original_ffid: row for row in analysis.rows if row.reference}
    last = by_ffid["6873"]
    assert last.association == "ASSIGNED" and last.corrected_ffid == "6873"
    assert last.target.row_index == len(analysis.target) - 1, "the sequence-consistent (final) EIVA row"
    assert last.pair.basis == "SEQUENCE" and last.pair.distance_m > 200 and last.qc_severity == "SEVERE"
    codes = {f.code for f in last.findings}
    assert {"RECORDER_POSITION_JUMP", "ASSOCIATION_DISTANCE_SEVERE", "ASSOCIATION_SEQUENCE_ONLY"} <= codes
    for ffid in ("6871", "6872"):
        assert by_ffid[ffid].association == "ASSIGNED" and by_ffid[ffid].qc_severity != "SEVERE"
    assert [by_ffid[f].target.row_index for f in ("6871", "6872", "6873")] == [len(analysis.target) - 3 + i for i in range(3)]


def test_no_recorder_record_is_discarded_for_distance(run):
    analysis, *_ = run
    assert all(row.association == "ASSIGNED" for row in analysis.rows if row.reference)
    assert max(p.distance_m for p in analysis.alignment.associations) > 200      # kept, and reported by QC
