from pathlib import Path

import pytest

from config import INVALID_COORDINATE
from shotlogfixer.correction import (CorrectionNotValidatedError, prepare_correction,
                                     save_fixed_eiva, save_fixed_pair, validate_serialized)
from shotlogfixer.models import RecorderRecord
from shotlogfixer.parsers import classify_recorder_row, parse_recorder


def write_pair(tmp_path: Path, eiva_rows: str, recorder_rows: str):
    eiva = tmp_path / "OS_A-1_LOG_EIVA.txt"
    recorder = tmp_path / "OS-A-1_header.txt"
    eiva.write_text("FFID,E(Spark),N(Spark),DATE,OTHER\n" + eiva_rows, encoding="utf-8")
    recorder.write_text("FFID SOU_X SOU_Y OTHER\n" + recorder_rows, encoding="utf-8")
    return eiva, recorder


def test_recorder_classification_variants(tmp_path):
    path = tmp_path / "rec.txt"
    path.write_text(
        "FFID SOU_X SOU_Y\n"
        "1 -214748.36480 -214748.36480\n"
        "2 -214748.36480 1\n3 1 -214748.36480\n"
        "4 NaN 1\n5 1 Infinity\n6 1\n7 2 3\n", encoding="utf-8")
    rows = parse_recorder(path)
    assert [classify_recorder_row(row) for row in rows] == ["NO_SHOT", "INVALID", "INVALID", "INVALID", "INVALID", "INVALID", "VALID"]


def test_bracketed_no_shot_resolves_and_formats_pair(tmp_path):
    eiva, recorder = write_pair(tmp_path,
        "101,0,0,2025-01-01,x\n102,1,0,2025-01-01,x\n103,10,0,2025-01-01,x\n553,20,0,2025-01-01,x\n554,30,0,2025-01-01,x\n",
        "101 10.20 0.10 keep\n542 -214748.36480 -214748.36480 sentinel\n543 30.10 0.20 keep\n")
    bundle = prepare_correction(eiva, recorder)
    assert bundle.plan.safe_to_build
    assert bundle.plan.dropped_eiva_only_count == 2
    assert bundle.plan.dropped_no_shot_count == 1
    assert bundle.validation and bundle.validation.passed
    assert "553" not in bundle.eiva_text
    assert "542" not in bundle.recorder_text
    assert "10.20" in bundle.recorder_text and "0.10" in bundle.recorder_text
    assert "2025-01-01" in bundle.eiva_text


@pytest.mark.parametrize("eiva_rows,recorder_rows", [
    ("101,10,0,d,x\n553,20,0,d,x\n", "101 10 0\n542 -214748.36480 -214748.36480\n"),
    ("553,20,0,d,x\n554,30,0,d,x\n", "542 -214748.36480 -214748.36480\n543 30 0\n"),
])
def test_no_shot_without_two_sided_anchors_blocks(tmp_path, eiva_rows, recorder_rows):
    eiva, recorder = write_pair(tmp_path, eiva_rows, recorder_rows)
    bundle = prepare_correction(eiva, recorder)
    assert not bundle.plan.safe_to_build
    assert bundle.validation and not bundle.validation.passed
    assert any("NO_SHOT" in reason or "unresolved" in reason for reason in bundle.plan.blocking_reasons)


def test_no_shot_count_mismatch_blocks(tmp_path):
    eiva, recorder = write_pair(tmp_path, "101,10,0,d,x\n553,20,0,d,x\n554,25,0,d,x\n555,30,0,d,x\n", "101 10 0\n542 -214748.36480 -214748.36480\n543 30 0\n")
    bundle = prepare_correction(eiva, recorder)
    assert not bundle.plan.safe_to_build
    assert any("count mismatch" in reason for reason in bundle.plan.blocking_reasons)


def test_invalid_recorder_blocks_and_writer_refuses(tmp_path):
    eiva, recorder = write_pair(tmp_path, "101,10,0,d,x\n", "101 -214748.36480 1\n")
    bundle = prepare_correction(eiva, recorder)
    assert not bundle.validation.passed
    with pytest.raises(CorrectionNotValidatedError):
        save_fixed_pair(bundle, tmp_path / "e_fixed.txt", tmp_path / "r_fixed.txt", [eiva, recorder])
    assert not (tmp_path / "e_fixed.txt").exists()


def test_raw_hashes_unchanged_after_successful_pair_write(tmp_path):
    eiva, recorder = write_pair(tmp_path, "101,10,0,d,x\n102,20,0,d,x\n", "1 10.01 0 keep\n2 20.01 0 keep\n")
    before = (eiva.read_bytes(), recorder.read_bytes())
    bundle = prepare_correction(eiva, recorder)
    outputs = save_fixed_pair(bundle, tmp_path / "e_fixed.txt", tmp_path / "r_fixed.txt", [eiva, recorder])
    assert all(path.exists() for path in outputs)
    assert (eiva.read_bytes(), recorder.read_bytes()) == before
    assert len(outputs[0].read_text().splitlines()) == len(outputs[1].read_text().splitlines())


def test_output_path_guard_and_explicit_overwrite(tmp_path):
    eiva, recorder = write_pair(tmp_path, "101,10,0,d,x\n", "1 10.01 0 keep\n")
    bundle = prepare_correction(eiva, recorder)
    with pytest.raises(ValueError):
        save_fixed_eiva(bundle, eiva)
    output = tmp_path / "fixed.txt"
    save_fixed_eiva(bundle, output)
    with pytest.raises(FileExistsError):
        save_fixed_eiva(bundle, output)
    save_fixed_eiva(bundle, output, overwrite=True)


def test_serialized_validator_rejects_bad_precision():
    result = validate_serialized("FFID,E(Spark),N(Spark)\n1,1.000,2.00\n", "FFID SOU_X SOU_Y\n1 1.00 2.00\n")
    assert not result.passed
    assert any("two decimals" in error for error in result.errors)
