"""Builders shared by the reconciliation tests."""
from pathlib import Path

from shotlogfixer import engine_cli
from shotlogfixer.alignment import align_records
from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.models import REFERENCE, TARGET, SourceRecord
from shotlogfixer.qc import run_qc

INTERVAL = 3.125
PARAMS = AnalysisParameters(INTERVAL)


def fmt(value):
    return value if isinstance(value, str) else f"{value:.2f}"


def write_reference(tmp_path: Path, rows, name="recorder.txt") -> Path:
    """Recorder log: whitespace delimited with the standard header.  rows: (ffid, x, y)."""
    path = tmp_path / name
    path.write_text("FFID SOU_X SOU_Y\n" + "".join(f"{f} {fmt(x)} {fmt(y)}\n" for f, x, y in rows),
                    encoding="utf-8", newline="\n")
    return path


def write_target(tmp_path: Path, rows, name="eiva.txt") -> Path:
    """EIVA-style log: CSV with a header and unrelated columns.  rows: (ffid, x, y)."""
    path = tmp_path / name
    path.write_text("FFID,E(Spark),N(Spark),DATE,NOTE\n" + "".join(
        f"{f},{fmt(x)},{fmt(y)},2025-01-01,row{i}\n" for i, (f, x, y) in enumerate(rows)), encoding="utf-8", newline="\n")
    return path


def analysis_for(reference_path, target_path, interval=INTERVAL):
    analysis, failure = engine_cli.prepare_analysis({"action": "analyse", "reference_path": str(reference_path),
                                                     "target_path": str(target_path), "shot_interval_m": interval})
    assert failure is None, failure
    return analysis


def reconcile(tmp_path, reference_rows, target_rows, interval=INTERVAL):
    ref, tgt = write_reference(tmp_path, reference_rows), write_target(tmp_path, target_rows)
    return ref, tgt, analysis_for(ref, tgt, interval)


def track(count, first_ffid=100, step=INTERVAL, x0=615190.23, y0=4645679.70):
    """A straight survey line: (ffid, x, y) rows one shot interval apart."""
    return [(first_ffid + i, x0 + step * i, y0) for i in range(count)]


def rec(role, index, x, y, ffid=None, classification="VALID", reason=""):
    return SourceRecord(role, index, index + 1, index + 1, "", (), str(ffid if ffid is not None else 100 + index),
                        x, y, classification, reason)


def reference_records(points, first_ffid=100):
    return [rec(REFERENCE, i, x, y, first_ffid + i) for i, (x, y) in enumerate(points)]


def target_records(points, first_ffid=1):
    return [rec(TARGET, i, x, y, first_ffid + i) if x is not None else
            rec(TARGET, i, None, None, first_ffid + i, "INVALID", "coordinate is missing or not a finite number")
            for i, (x, y) in enumerate(points)]


def qc_for(reference, target, params=PARAMS):
    alignment = align_records(reference, target, params)
    return alignment, run_qc(reference, target, alignment, params)


def codes(findings, code=None, scope=None):
    return [f for f in findings if (code is None or f.code == code) and (scope is None or f.scope == scope)]
