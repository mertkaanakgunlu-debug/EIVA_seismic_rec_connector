import json

from shotlogfixer.engine_cli import analyse, dispatch


def write_fixture(tmp_path):
    eiva = tmp_path / "eiva.csv"
    eiva.write_text("FFID,E(Spark),N(Spark),DATE\n101,1,2,2025-01-01\n102,3,4,2025-01-01\n", encoding="utf-8")
    recorder = tmp_path / "recorder.txt"
    recorder.write_text("FFID SOU_X SOU_Y\n1 1 2\n2 3 4\n", encoding="utf-8")
    return eiva, recorder


def test_analyse_json_contract_and_fields(tmp_path):
    eiva, recorder = write_fixture(tmp_path)
    response = analyse(str(eiva), str(recorder), 3.125)
    assert response["ok"] is True
    assert {key: response["summary"][key] for key in ("eiva_rows", "recorder_rows", "matched", "eiva_only", "recorder_invalid", "review", "total_issues")} == {
        "eiva_rows": 2,
        "recorder_rows": 2,
        "matched": 2,
        "eiva_only": 0,
        "recorder_invalid": 0,
        "review": 0,
        "total_issues": 0,
    }
    assert response["eiva_headers"] == ["FFID", "E(Spark)", "N(Spark)", "DATE"]
    assert response["records"][0]["eiva_values"]["DATE"] == "2025-01-01"


def test_structured_error_response(tmp_path):
    response = dispatch({"action": "analyse", "eiva_path": str(tmp_path / "missing"), "recorder_path": "", "shot_interval_m": 3.125})
    assert response["ok"] is False
    assert response["error"]["code"] == "FILE_NOT_FOUND"
    assert "traceback" not in json.dumps(response).lower()


def test_qc_export_command_uses_python_report_logic(tmp_path):
    eiva, recorder = write_fixture(tmp_path)
    output = tmp_path / "out.txt"
    response = dispatch({"action": "export_qc", "eiva_path": str(eiva), "recorder_path": str(recorder), "output_path": str(output), "shot_interval_m": 3.125})
    assert response["ok"] is True
    assert output.read_text(encoding="utf-8").splitlines()[0].startswith("eiva_ffid\teiva_easting")
    exported = output.read_text(encoding="utf-8-sig")
    assert len(exported.splitlines()) >= 3
    assert "# shot_interval_m=3.125" in exported
    assert "# match_tolerance_m=1.5625" in exported
