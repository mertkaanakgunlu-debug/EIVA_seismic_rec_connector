"""Structured JSON boundary for the existing ShotLogFixer engine.

The Electron main process talks to this module over stdin/stdout.  Domain
logic remains in the parser, matcher, QC, and report modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .matcher import match_records
from .parsers import parse_eiva, parse_recorder
from .qc import anomaly_event_count, ffid_discontinuities
from .report import export_csv


def _error(code: str, message: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    return payload


def _validate_file(value: Any, label: str) -> Path | dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return _error(f"MISSING_{label.upper()}_FILE", f"Select an {label} file.")
    path = Path(value).expanduser()
    if not path.exists():
        return _error("FILE_NOT_FOUND", f"The selected {label} file does not exist.", str(path))
    if not path.is_file():
        return _error("PATH_NOT_FILE", f"The selected {label} path is not a file.", str(path))
    return path


def _record_position(result: Any, eiva_records: list[Any], result_index: int) -> int:
    if result.eiva_record:
        for index, record in enumerate(eiva_records):
            if record.source_line_number == result.eiva_record.source_line_number:
                return index + 1
    for later in range(result_index + 1, len(eiva_records)):
        if eiva_records[later].source_line_number == getattr(result.eiva_record, "source_line_number", None):
            return later + 1
    for index in range(result_index - 1, -1, -1):
        if index < len(eiva_records):
            return index + 1
    return min(result_index + 1, len(eiva_records)) if eiva_records else 0


def _serialize_result(result: Any, eiva_records: list[Any], index: int) -> dict[str, Any]:
    eiva = result.eiva_record
    recorder = result.recorder_record
    return {
        "id": f"result-{index + 1}",
        "result_index": index,
        "acquisition_position": _record_position(result, eiva_records, index),
        "eiva_ffid": eiva.original_ffid if eiva else None,
        "recorder_ffid": recorder.ffid if recorder else None,
        "eiva_easting": eiva.easting_spark if eiva else None,
        "eiva_northing": eiva.northing_spark if eiva else None,
        "recorder_x": recorder.source_x if recorder else None,
        "recorder_y": recorder.source_y if recorder else None,
        "distance_m": result.distance_m,
        "status": result.status,
        "diagnostic": result.diagnostic,
        "eiva_values": dict(eiva.original_values_by_column) if eiva else {},
    }


def analyse(eiva_path: Any, recorder_path: Any) -> dict[str, Any]:
    eiva = _validate_file(eiva_path, "EIVA")
    if isinstance(eiva, dict):
        return eiva
    recorder = _validate_file(recorder_path, "recorder")
    if isinstance(recorder, dict):
        return recorder
    try:
        eiva_records = parse_eiva(eiva)
    except PermissionError as exc:
        return _error("EIVA_PERMISSION_DENIED", "Unable to open the selected EIVA log.", str(exc))
    except (OSError, ValueError) as exc:
        return _error("INVALID_EIVA_FILE", "Unable to parse the selected EIVA log.", str(exc))
    try:
        recorder_records = parse_recorder(recorder)
    except PermissionError as exc:
        return _error("RECORDER_PERMISSION_DENIED", "Unable to open the selected recorder log.", str(exc))
    except (OSError, ValueError) as exc:
        return _error("INVALID_RECORDER_FILE", "Unable to parse the selected recorder log.", str(exc))

    results = match_records(eiva_records, recorder_records)
    counts = {status: sum(result.status == status for result in results) for status in (
        "MATCHED", "EIVA_ONLY", "RECORDER_INVALID", "REVIEW"
    )}
    return {
        "ok": True,
        "summary": {
            "eiva_rows": len(eiva_records),
            "recorder_rows": len(recorder_records),
            "matched": counts["MATCHED"],
            "eiva_only": counts["EIVA_ONLY"],
            "recorder_invalid": counts["RECORDER_INVALID"],
            "review": counts["REVIEW"],
            "total_issues": anomaly_event_count(results),
        },
        "ffid_jumps": [{"from": before, "to": after} for before, after in ffid_discontinuities(eiva_records)],
        "eiva_headers": list(eiva_records[0].original_values_by_column) if eiva_records else [],
        "records": [_serialize_result(result, eiva_records, index) for index, result in enumerate(results)],
    }


def export_qc(eiva_path: Any, recorder_path: Any, output_path: Any) -> dict[str, Any]:
    eiva = _validate_file(eiva_path, "EIVA")
    if isinstance(eiva, dict):
        return eiva
    recorder = _validate_file(recorder_path, "recorder")
    if isinstance(recorder, dict):
        return recorder
    if not isinstance(output_path, str) or not output_path.strip():
        return _error("MISSING_EXPORT_PATH", "Choose a destination for the QC CSV.")
    output = Path(output_path).expanduser()
    try:
        results = match_records(parse_eiva(eiva), parse_recorder(recorder))
        export_csv(output, results)
    except PermissionError as exc:
        return _error("EXPORT_PERMISSION_DENIED", "Unable to write the QC CSV file.", str(exc))
    except (OSError, ValueError) as exc:
        return _error("EXPORT_FAILED", "Unable to export the QC CSV file.", str(exc))
    return {"ok": True, "path": str(output), "rows": len(results)}


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "analyse")
    if action == "analyse":
        return analyse(payload.get("eiva_path"), payload.get("recorder_path"))
    if action in {"export", "export_qc"}:
        return export_qc(payload.get("eiva_path"), payload.get("recorder_path"), payload.get("output_path"))
    return _error("UNKNOWN_ACTION", f"Unsupported engine action: {action}")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            response = _error("INVALID_REQUEST", "The engine request must be a JSON object.")
        else:
            response = dispatch(payload)
    except json.JSONDecodeError as exc:
        response = _error("INVALID_REQUEST", "The engine request was not valid JSON.", str(exc))
    except Exception as exc:  # Keep tracebacks out of the renderer contract.
        response = _error("ENGINE_FAILURE", "The ShotLogFixer engine could not complete the request.", str(exc))
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
