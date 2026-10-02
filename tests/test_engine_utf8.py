"""The engine speaks UTF-8 JSON to Electron on every machine.

A Windows pipe defaults to the ANSI code page of the machine (cp1254 on a Turkish install), while Electron writes the request and
reads the response as UTF-8.  These tests run the real engine process under legacy code pages and check that non-ASCII text
survives both directions: file paths in the request, and raw EIVA content and paths in the response.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import track, write_reference

ROOT = Path(__file__).resolve().parents[1]
FOLDER = "Sürvey_Ω°_界"                              # characters from several scripts, none of them all in one code page
DATE = "25.09.2026 041°57'"
NOTE = "Şişli-açıklama-界"


def run_engine(request: dict, code_page: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": code_page, "PYTHONUTF8": "0"}      # emulate a machine with a legacy code page
    return subprocess.run([sys.executable, "-m", "shotlogfixer.engine_cli"], input=json.dumps(request).encode("utf-8"),
                          capture_output=True, cwd=ROOT, env=env, timeout=120)


@pytest.fixture
def files(tmp_path):
    folder = tmp_path / FOLDER
    folder.mkdir()
    reference = write_reference(folder, track(4, first_ffid=500), name="kaydedici_Ω.txt")
    rows = [f"{f},{x:.2f},{y:.2f},{DATE},{NOTE}\n" for f, x, y in track(5, first_ffid=1)]
    target = folder / "eiva_ş_界.csv"
    target.write_bytes(("FFID,E(Spark),N(Spark),DATE,NOTE\n" + "".join(rows)).encode("utf-8"))
    return folder, reference, target


def request(reference, target, **extra):
    return {"reference_path": str(reference), "target_path": str(target), "shot_interval_m": 3.125, **extra}


@pytest.mark.parametrize("code_page", ["cp1252", "cp1254", "ascii"])
def test_non_ascii_paths_and_raw_content_survive_the_engine_round_trip(files, code_page):
    folder, reference, target = files
    process = run_engine({**request(reference, target), "action": "analyse"}, code_page)
    assert process.returncode == 0, process.stderr.decode("utf-8", "replace")
    response = json.loads(process.stdout.decode("utf-8"))             # strict: the response must be valid UTF-8
    assert response["ok"] is True and response["summary"]["assigned"] == 4
    raw = response["records"][1]["target_values"]
    assert raw["DATE"] == DATE and raw["NOTE"] == NOTE, "raw EIVA content must arrive intact"


@pytest.mark.parametrize("code_page", ["cp1252", "ascii"])
def test_corrected_copy_is_written_to_a_non_ascii_path_with_content_preserved(files, code_page):
    folder, reference, target = files
    output = folder / "düzeltilmiş_Ω.csv"
    process = run_engine({**request(reference, target, output_path=str(output)), "action": "save_corrected_target"}, code_page)
    assert process.returncode == 0, process.stderr.decode("utf-8", "replace")
    response = json.loads(process.stdout.decode("utf-8"))
    assert response["ok"] is True and response["path"] == str(output)
    data = output.read_bytes().decode("utf-8")
    assert data.count(NOTE) == 4 and data.count(DATE) == 4, "only the FFID field changes; non-ASCII fields stay byte for byte"
    assert [line.split(",")[0] for line in data.splitlines()[1:]] == ["500", "501", "502", "503"]


@pytest.mark.parametrize("code_page", ["cp1252", "ascii"])
def test_error_responses_quote_non_ascii_paths_exactly(files, code_page):
    folder, reference, _ = files
    missing = folder / "yok_Ω_界.csv"
    process = run_engine({**request(reference, missing), "action": "analyse"}, code_page)
    response = json.loads(process.stdout.decode("utf-8"))
    assert response["ok"] is False and "yok_Ω_界.csv" in json.dumps(response, ensure_ascii=False)
