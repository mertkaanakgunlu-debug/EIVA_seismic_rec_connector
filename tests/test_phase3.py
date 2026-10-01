from pathlib import Path

import pytest

from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.correction import prepare_correction
from shotlogfixer.engine_cli import analyse, dispatch


def pair(tmp_path: Path, eiva_x, recorder_x):
    eiva = tmp_path / "eiva.txt"
    recorder = tmp_path / "recorder.txt"
    eiva.write_text("FFID,E(Spark),N(Spark)\n" + "\n".join(f"{100+i},{x},0" for i, x in enumerate(eiva_x)) + "\n")
    recorder.write_text("FFID SOU_X SOU_Y\n" + "\n".join(f"{100+i} {x} 0" for i, x in enumerate(recorder_x)) + "\n")
    return eiva, recorder


def test_analysis_parameters_derive_tolerance_and_reject_invalid():
    assert AnalysisParameters(3.125).match_tolerance_m == 1.5625
    for value in (None, "", 0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            AnalysisParameters(value)


def test_engine_rejects_missing_or_invalid_interval(tmp_path):
    eiva, recorder = pair(tmp_path, [0], [0])
    for value in (None, "", "0", "Infinity", "-2"):
        response = dispatch({"action": "analyse", "eiva_path": str(eiva), "recorder_path": str(recorder), "shot_interval_m": value})
        assert response["ok"] is False and response["error"]["code"] == "INVALID_SHOT_INTERVAL"


def test_dynamic_tolerance_exact_boundary_and_interval_changes_match(tmp_path):
    eiva, recorder = pair(tmp_path, [0], [1.5625])
    assert prepare_correction(eiva, recorder, AnalysisParameters(3.125)).results[0].status == "MATCHED"
    eiva, recorder = pair(tmp_path, [0], [1.5625001])
    assert prepare_correction(eiva, recorder, AnalysisParameters(3.125)).results[0].status == "REVIEW"
    assert prepare_correction(eiva, recorder, AnalysisParameters(5)).results[0].status == "MATCHED"


def test_four_and_five_step_gap_off_by_one_and_no_synthetic_recorder(tmp_path):
    eiva, recorder = pair(tmp_path, [15, 20, 25, 30, 35], [15, 35])
    bundle = prepare_correction(eiva, recorder, AnalysisParameters(5))
    gap = bundle.recorder_gaps[0]
    assert (gap.gap_span_steps, gap.estimated_missing_positions) == (4, 3)
    assert gap.eiva_only_indices == [1, 2, 3]
    assert [r.ffid for r in bundle.recorder_records] == ["100", "101"]
    eiva, recorder = pair(tmp_path, [15, 40], [15, 40])
    gap = prepare_correction(eiva, recorder, AnalysisParameters(5)).recorder_gaps[0]
    assert (gap.gap_span_steps, gap.estimated_missing_positions) == (5, 4)


def test_shared_gap_is_warning_only_and_partial_eiva_is_safe(tmp_path):
    eiva, recorder = pair(tmp_path, [15, 35], [15, 35])
    bundle = prepare_correction(eiva, recorder, AnalysisParameters(5))
    assert bundle.recorder_gaps[0].classification == "RECORDER_GAP_SHARED"
    assert bundle.plan.safe_to_build
    eiva, recorder = pair(tmp_path, [15, 20, 35], [15, 35])
    bundle = prepare_correction(eiva, recorder, AnalysisParameters(5))
    assert bundle.plan.safe_to_build and bundle.recorder_gaps[0].eiva_only_indices == [1]


def test_off_slot_gap_fails_closed_and_response_contains_parameters(tmp_path):
    eiva, recorder = pair(tmp_path, [15, 22.5, 35], [15, 35])
    bundle = prepare_correction(eiva, recorder, AnalysisParameters(5))
    assert not bundle.plan.safe_to_build
    response = analyse(str(eiva), str(recorder), "5")
    assert response["parameters"] == {"shot_interval_m": 5.0, "match_tolerance_m": 2.5}
    assert response["recorder_gaps"][0]["estimated_missing_positions"] == 3
