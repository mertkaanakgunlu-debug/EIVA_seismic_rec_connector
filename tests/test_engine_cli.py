"""The JSON boundary: request validation, response schema, and the correction/QC separation in the payload."""
import json

import pytest

from shotlogfixer import engine_cli
from shotlogfixer.engine_cli import analyse, dispatch

from helpers import track, write_reference, write_target


def pair(tmp_path, reference=None, target=None):
    reference = reference if reference is not None else track(4, first_ffid=500)
    target = target if target is not None else track(5, first_ffid=1)
    return write_reference(tmp_path, reference), write_target(tmp_path, target)


def request(ref, tgt, **extra):
    return {"reference_path": str(ref), "target_path": str(tgt), "shot_interval_m": 3.125, **extra}


def test_analyse_contract_separates_association_correction_and_qc(tmp_path):
    ref, tgt = pair(tmp_path)
    response = analyse(request(ref, tgt))
    assert response["ok"] is True
    summary = response["summary"]
    assert (summary["reference_rows"], summary["reference_valid"], summary["target_rows"]) == (4, 4, 5)
    assert (summary["assigned"], summary["target_only"], summary["corrected_rows"], summary["expected_rows"]) == (4, 1, 4, 4)
    assert response["correction"]["safe"] is True and response["correction"]["blockers"] == []
    assert set(response["qc"]) == {"summary", "findings", "ffid_jumps"}
    assert response["parameters"]["normal_distance_m"] == 1.5625 and "match_tolerance_m" not in response["parameters"]
    assert response["target_headers"] == ["FFID", "E(Spark)", "N(Spark)", "DATE", "NOTE"]
    assert set(response["input_formats"]) == {"reference", "target"}
    assert set(response["input_hashes"]) == {"reference", "target"}
    json.dumps(response)
    first = response["records"][0]
    assert set(first) >= {"id", "association", "reference_ffid", "target_ffid", "corrected_ffid", "reference_x", "target_x",
                          "distance_m", "basis", "confidence", "qc_severity", "qc_codes", "diagnostic", "target_values",
                          "acquisition_position"}
    assert first["association"] == "ASSIGNED" and first["corrected_ffid"] == "500" and first["target_values"]["NOTE"] == "row0"
    assert [r["association"] for r in response["records"]].count("TARGET_ONLY") == 1


def test_assigned_row_with_a_qc_finding_keeps_its_assignment_in_the_payload(tmp_path):
    reference = track(4, first_ffid=600)
    reference[2] = (602, reference[2][1] + 300.0, reference[2][2])
    ref, tgt = pair(tmp_path, reference, track(4, first_ffid=1))
    response = analyse(request(ref, tgt))
    row = next(r for r in response["records"] if r["reference_ffid"] == "602")
    assert (row["association"], row["corrected_ffid"], row["qc_severity"]) == ("ASSIGNED", "602", "SEVERE")
    assert "RECORDER_POSITION_SPIKE" in row["qc_codes"] or "RECORDER_POSITION_JUMP" in row["qc_codes"]
    assert response["correction"]["safe"] is True
    finding = next(f for f in response["qc"]["findings"] if f["code"] == "ASSOCIATION_DISTANCE_SEVERE")
    assert finding["row_id"] == row["id"] and finding["metrics"]["distance_m"] > 290


def test_ffid_jumps_come_from_the_authoritative_recorder(tmp_path):
    reference = [(100, 0.0, 0.0), (101, 3.1, 0.0), (105, 6.2, 0.0), (106, 9.3, 0.0)]
    ref, tgt = pair(tmp_path, reference, track(4, first_ffid=1, x0=0.0, y0=0.0))
    jumps = analyse(request(ref, tgt))["qc"]["ffid_jumps"]
    assert [(j["from"], j["to"], j["kind"]) for j in jumps] == [(101, 105, "GAP")]


def test_legacy_request_keys_are_still_accepted(tmp_path):
    ref, tgt = pair(tmp_path)
    response = dispatch({"action": "analyse", "recorder_path": str(ref), "eiva_path": str(tgt), "shot_interval_m": 3.125})
    assert response["ok"] and response["summary"]["assigned"] == 4


def test_structured_errors_never_leak_tracebacks(tmp_path):
    response = dispatch({"action": "analyse", "reference_path": str(tmp_path / "missing"), "target_path": "", "shot_interval_m": 3.125})
    assert response["ok"] is False and response["error"]["code"] == "FILE_NOT_FOUND"
    assert "traceback" not in json.dumps(response).lower()
    ref, _ = pair(tmp_path)
    missing = dispatch({"action": "analyse", "reference_path": str(ref), "target_path": "", "shot_interval_m": 3.125})
    assert missing["error"]["code"] == "MISSING_TARGET_FILE"
    assert dispatch({"action": "nope"})["error"]["code"] == "UNKNOWN_ACTION"
    assert dispatch({"action": "save_fixed_pair"})["error"]["code"] == "UNKNOWN_ACTION", "the recorder is never rewritten"


def test_engine_rejects_missing_or_invalid_interval(tmp_path):
    ref, tgt = pair(tmp_path)
    for value in (None, "", "0", "Infinity", "-2"):
        response = dispatch({**request(ref, tgt), "action": "analyse", "shot_interval_m": value})
        assert response["ok"] is False and response["error"]["code"] == "INVALID_SHOT_INTERVAL"
    assert dispatch({**request(ref, tgt), "shot_interval_m": "3,125"})["ok"], "a decimal comma is accepted"


def test_unreadable_files_are_attributed_to_the_right_input(tmp_path):
    ref = tmp_path / "recorder.txt"
    ref.write_text("FFID SOU_X SOU_Y\n1 2\n2 3\n3 4\n")
    tgt = write_target(tmp_path, track(3))
    response = analyse(request(ref, tgt))
    assert response["ok"] is False and response["error"]["code"] in {"FORMAT_NOT_READY", "INVALID_REFERENCE_FILE"}


def test_qc_export_keeps_decisions_and_observations_apart(tmp_path):
    reference = track(5, first_ffid=700)
    reference[4] = (704, reference[4][1] + 200.0, reference[4][2] + 100.0)
    ref, tgt = pair(tmp_path, reference, track(6, first_ffid=1))
    output = tmp_path / "qc.txt"
    response = dispatch({**request(ref, tgt), "action": "export_qc", "output_path": str(output)})
    assert response["ok"] and response["rows"] == 6
    text = output.read_text(encoding="utf-8")
    header, *rows = text.splitlines()
    assert header.split("\t") == ["reference_ffid", "target_original_ffid", "corrected_ffid", "reference_x", "reference_y", "target_x",
                                  "target_y", "distance_m", "association", "association_code", "confidence", "qc_status", "qc_codes",
                                  "diagnostic"]
    last = next(r for r in rows if r.startswith("704\t")).split("\t")
    assert last[2] == "704" and last[9] == "ASSIGNED" and last[11] == "Severe"
    for section in ("[CORRECTION]", "[QC_SUMMARY]", "[QC_FINDINGS]", "[INPUT_FORMATS]"):
        assert section in text
    assert "status=READY" in text and "corrected_rows=5" in text and "expected_rows=5" in text
    assert "reference_profile_name=" in text and "target_ffid_column=" in text
    assert "blocker\t" not in text


def test_qc_export_lists_blockers_when_correction_is_blocked(tmp_path):
    ref, tgt = pair(tmp_path, track(5), track(4))
    output = tmp_path / "qc.txt"
    assert dispatch({**request(ref, tgt), "action": "export_qc", "output_path": str(output)})["ok"]
    text = output.read_text(encoding="utf-8")
    assert "status=BLOCKED" in text and "blocker\tINSUFFICIENT_TARGET_ROWS" in text


def test_save_action_alias_and_blocked_save_report(tmp_path):
    ref, tgt = pair(tmp_path)
    out = tmp_path / "fixed.txt"
    saved = dispatch({**request(ref, tgt), "action": "save_fixed_eiva", "output_path": str(out)})
    assert saved["ok"] and saved["rows"] == 4 and out.exists()
    again = dispatch({**request(ref, tgt), "action": "save_corrected_target", "output_path": str(out)})
    assert again["error"]["code"] == "OUTPUT_EXISTS"
    ref2, tgt2 = pair(tmp_path, track(5), track(4))
    blocked = dispatch({**request(ref2, tgt2), "action": "save_corrected_target", "output_path": str(tmp_path / "x.txt")})
    assert blocked["error"]["code"] == "SAVE_BLOCKED" and not (tmp_path / "x.txt").exists()
    nopath = dispatch({**request(ref, tgt), "action": "save_corrected_target"})
    assert nopath["error"]["code"] == "MISSING_OUTPUT_PATH"
