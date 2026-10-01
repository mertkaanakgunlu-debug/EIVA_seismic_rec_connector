from pathlib import Path
import json

from shotlogfixer.engine_cli import analyse, dispatch
from shotlogfixer.format_detection import detect_text
from shotlogfixer.format_profiles import ProfileStore


def test_pronav_headerless_comma_is_detected_and_analyzed(tmp_path: Path):
    eiva = tmp_path / "eiva.csv"
    recorder = tmp_path / "pronav.txt"
    eiva.write_text("FFID,E(Spark),N(Spark)\n101,615190.23,4645679.70\n102,615192.76,4645681.13\n", encoding="utf-8")
    recorder.write_text("101,615190.23,4645679.7\n102,615192.76,4645681.13\n", encoding="utf-8")
    result = analyse(eiva, recorder, 3.125)
    assert result["ok"]
    profile = result["input_formats"]["recorder"]
    assert profile["delimiter"] == "comma"
    assert profile["header"] == "ABSENT"
    assert profile["column_mapping"] == {"FFID": 0, "RECORDER_X": 1, "RECORDER_Y": 2}
    assert result["summary"]["recorder_invalid"] == 0


def test_text_identifier_does_not_become_numeric_ffid():
    profile, _ = detect_text("LINE001,1,2\nLINE002,3,4\n", "RECORDER")
    assert profile.confidence == "Unresolved"
    assert "FFID" not in profile.mapping


def test_user_profile_store_round_trip_and_builtin_read_only(tmp_path: Path):
    detected, _ = detect_text("101,1,2\n102,3,4\n", "RECORDER")
    store = ProfileStore(tmp_path / "format-profiles.json")
    saved = store.save(detected, "Vessel X")
    assert store.load()[0].profile_hash == saved.profile_hash
    listed = dispatch({"action": "list_profiles"})
    assert any(item["id"] == "builtin-pronav-3col" for item in listed["profiles"])
    deleted = dispatch({"action": "delete_profile", "profile_id": "builtin-pronav-3col"})
    assert deleted["ok"] is False


def test_malformed_profile_mapping_is_rejected_as_profile_error():
    detected, _ = detect_text("101,1,2\n102,3,4\n", "RECORDER")
    payload = detected.as_dict()
    payload["column_mapping"] = [("FFID", 0)]
    result = dispatch({"action": "save_profile", "profile": payload, "name": "Broken"})
    assert result["ok"] is False
    assert result["error"]["code"] == "PROFILE_OPERATION_FAILED"


def test_corrupt_profile_store_is_reported_as_invalid_store(tmp_path: Path):
    path = tmp_path / "format-profiles.json"
    path.write_text(json.dumps({"schema_version": 1, "profiles": {}}), encoding="utf-8")
    try:
        ProfileStore(path).load()
    except ValueError as exc:
        assert "profile list" in str(exc)
    else:
        raise AssertionError("corrupt profile store should fail closed")
