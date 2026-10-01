"""Structured JSON boundary for the existing ShotLogFixer engine.

The Electron main process talks to this module over stdin/stdout.  Domain
logic remains in the parser, matcher, QC, and report modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .correction import (CorrectionNotValidatedError, prepare_correction, save_fixed_eiva,
                         save_fixed_pair, sha256_file)
from .analysis_parameters import AnalysisParameters
from .gap_analysis import analyse_recorder_gaps
from .matcher import match_records
from .parsers import parse_eiva, parse_recorder
from .qc import ffid_discontinuities, total_issue_count
from .report import export_csv, export_txt
from .version import __version__


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
        "gap_event_ids": result.gap_event_ids,
        "eiva_values": dict(eiva.original_values_by_column) if eiva else {},
    }


def _parameters(value: Any) -> AnalysisParameters | dict[str, Any]:
    if isinstance(value, str): value = value.replace(",", ".")
    try:
        return AnalysisParameters(value)
    except ValueError as exc:
        return _error("INVALID_SHOT_INTERVAL", "Enter a finite positive Shot Interval in metres.", str(exc))


def analyse(eiva_path: Any, recorder_path: Any, shot_interval_m: Any = None) -> dict[str, Any]:
    parameters = _parameters(shot_interval_m)
    if isinstance(parameters, dict): return parameters
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

    try:
        bundle = prepare_correction(eiva, recorder, parameters)
    except (OSError, ValueError) as exc:
        return _error("CORRECTION_FAILED", "Unable to build the correction plan.", str(exc))
    results = bundle.results
    counts = {status: sum(result.status == status for result in results) for status in (
        "MATCHED", "EIVA_ONLY", "NO_SHOT", "RECORDER_INVALID", "REVIEW"
    )}
    # A resolved NO_SHOT appears once as a recorder event; unresolved windows
    # remain visible as REVIEW records and therefore remain counted separately.
    summary = {
        "eiva_rows": len(eiva_records),
        "recorder_rows": len(recorder_records),
        "matched": counts["MATCHED"],
        "eiva_only": counts["EIVA_ONLY"],
        "recorder_invalid": counts["RECORDER_INVALID"],
        "review": counts["REVIEW"],
        "total_issues": total_issue_count(results),
    }
    if shot_interval_m != 2.0:
        summary.update({"recorder_gap_count": len(bundle.recorder_gaps),
                        "unexplained_missing_positions": sum(g.unexplained_missing_positions for g in bundle.recorder_gaps)})
    if counts["NO_SHOT"]:
        summary["no_shot"] = counts["NO_SHOT"]
    validation = bundle.validation.as_dict() if bundle.validation else {"passed": False, "errors": ["missing validation"]}
    return {
        "ok": True,
        "summary": summary,
        "parameters": parameters.as_dict(),
        "recorder_gaps": [gap.as_dict() for gap in bundle.recorder_gaps],
        "correction": {
            "safe": bundle.plan.safe_to_build,
            "retained": bundle.plan.matched_count,
            "eiva_only_removed": bundle.plan.dropped_eiva_only_count,
            "no_shot_removed": bundle.plan.dropped_no_shot_count,
            "blocking_reasons": bundle.plan.blocking_reasons,
            "actions": [{"action": action.action_type, "eiva_ffid": action.original_eiva_ffid,
                         "target_ffid": action.target_ffid, "recorder_ffid": action.recorder_ffid,
                         "eiva_source_index": action.eiva_source_index,
                         "recorder_source_index": action.recorder_source_index,
                         "status": action.status, "reason": action.reason,
                         "distance_m": action.coordinate_distance_m, "gap_event_id": action.gap_event_id} for action in bundle.plan.actions],
        },
        "validation": validation,
        "input_hashes": bundle.input_hashes,
        "ffid_jumps": [{"from": before, "to": after} for before, after in ffid_discontinuities(eiva_records)],
        "eiva_headers": list(eiva_records[0].original_values_by_column) if eiva_records else [],
        "records": [_serialize_result(result, eiva_records, index) for index, result in enumerate(results)],
    }


def _prepare_for_save(eiva_path: Any, recorder_path: Any, shot_interval_m: Any = None):
    parameters = _parameters(shot_interval_m)
    if isinstance(parameters, dict): return parameters
    eiva = _validate_file(eiva_path, "EIVA")
    if isinstance(eiva, dict): return eiva
    recorder = _validate_file(recorder_path, "recorder")
    if isinstance(recorder, dict): return recorder
    try:
        return prepare_correction(eiva, recorder, parameters)
    except (OSError, ValueError) as exc:
        return _error("CORRECTION_FAILED", "Unable to build the correction plan.", str(exc))


def save_eiva(eiva_path: Any, recorder_path: Any, output_path: Any, overwrite: bool = False, shot_interval_m: Any = None) -> dict[str, Any]:
    bundle = _prepare_for_save(eiva_path, recorder_path, shot_interval_m)
    if isinstance(bundle, dict): return bundle
    if not isinstance(output_path, str) or not output_path.strip(): return _error("MISSING_OUTPUT_PATH", "Choose a fixed EIVA destination.")
    try:
        output = save_fixed_eiva(bundle, output_path, [Path(eiva_path), Path(recorder_path)], overwrite)
    except FileExistsError as exc: return _error("OUTPUT_EXISTS", "The fixed EIVA output already exists; confirm overwrite.", str(exc))
    except (CorrectionNotValidatedError, OSError, ValueError) as exc: return _error("SAVE_BLOCKED", "The fixed EIVA file was not written.", str(exc))
    return {"ok": True, "path": str(output), "rows": bundle.validation.fixed_eiva_count, "validation": bundle.validation.as_dict(), "raw_hashes_after": {"eiva": sha256_file(eiva_path), "recorder": sha256_file(recorder_path)}}


def save_pair(eiva_path: Any, recorder_path: Any, eiva_output: Any, recorder_output: Any, overwrite: bool = False, shot_interval_m: Any = None) -> dict[str, Any]:
    bundle = _prepare_for_save(eiva_path, recorder_path, shot_interval_m)
    if isinstance(bundle, dict): return bundle
    if not isinstance(eiva_output, str) or not eiva_output.strip() or not isinstance(recorder_output, str) or not recorder_output.strip():
        return _error("MISSING_OUTPUT_PATH", "Choose destinations for both fixed pair files.")
    try:
        outputs = save_fixed_pair(bundle, eiva_output, recorder_output, [Path(eiva_path), Path(recorder_path)], overwrite)
    except FileExistsError as exc: return _error("OUTPUT_EXISTS", "A fixed pair output already exists; confirm overwrite.", str(exc))
    except (CorrectionNotValidatedError, OSError, ValueError) as exc: return _error("SAVE_BLOCKED", "The fixed pair was not written.", str(exc))
    return {"ok": True, "eiva_path": str(outputs[0]), "recorder_path": str(outputs[1]), "rows": bundle.validation.fixed_eiva_count,
            "validation": bundle.validation.as_dict(), "raw_hashes_after": {"eiva": sha256_file(eiva_path), "recorder": sha256_file(recorder_path)}}


def export_qc(eiva_path: Any, recorder_path: Any, output_path: Any, shot_interval_m: Any = None) -> dict[str, Any]:
    parameters = _parameters(shot_interval_m)
    if isinstance(parameters, dict): return parameters
    eiva = _validate_file(eiva_path, "EIVA")
    if isinstance(eiva, dict):
        return eiva
    recorder = _validate_file(recorder_path, "recorder")
    if isinstance(recorder, dict):
        return recorder
    if not isinstance(output_path, str) or not output_path.strip():
        return _error("MISSING_EXPORT_PATH", "Choose a destination for the QC TXT.")
    output = Path(output_path).expanduser()
    try:
        eiva_records, recorder_records = parse_eiva(eiva), parse_recorder(recorder)
        raw_results = match_records(eiva_records, recorder_records, parameters)
        gaps = analyse_recorder_gaps(eiva_records, recorder_records, raw_results, parameters)
        # `.txt` is the product format. Keep `.csv` as a legacy direct-API
        # compatibility path for existing integrations, never selected by the UI.
        if output.suffix.lower() == ".csv":
            export_csv(output, raw_results)
        else:
            # Export the same resolved records and gap attribution the operator
            # reviewed; retain the legacy raw CSV API above for integrations.
            bundle = prepare_correction(eiva, recorder, parameters)
            raw_results, gaps = bundle.results, bundle.recorder_gaps
            export_txt(output, raw_results, parameters, gaps)
    except PermissionError as exc:
        return _error("EXPORT_PERMISSION_DENIED", "Unable to write the QC TXT file.", str(exc))
    except (OSError, ValueError) as exc:
        return _error("EXPORT_FAILED", "Unable to export the QC TXT file.", str(exc))
    return {"ok": True, "path": str(output), "rows": len(raw_results), "parameters": parameters.as_dict(), "recorder_gap_count": len(gaps)}


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "analyse")
    if action == "analyse":
        return analyse(payload.get("eiva_path"), payload.get("recorder_path"), payload.get("shot_interval_m"))
    if action in {"export", "export_qc"}:
        return export_qc(payload.get("eiva_path"), payload.get("recorder_path"), payload.get("output_path"), payload.get("shot_interval_m"))
    if action == "save_fixed_eiva":
        return save_eiva(payload.get("eiva_path"), payload.get("recorder_path"), payload.get("output_path"), bool(payload.get("overwrite")), payload.get("shot_interval_m"))
    if action == "save_fixed_pair":
        return save_pair(payload.get("eiva_path"), payload.get("recorder_path"), payload.get("eiva_output"), payload.get("recorder_output"), bool(payload.get("overwrite")), payload.get("shot_interval_m"))
    return _error("UNKNOWN_ACTION", f"Unsupported engine action: {action}")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            response = _error("INVALID_REQUEST", "The engine request must be a JSON object.")
        else:
            response = dispatch(payload)
        response.setdefault("version", __version__)
    except json.JSONDecodeError as exc:
        response = _error("INVALID_REQUEST", "The engine request was not valid JSON.", str(exc))
        response["version"] = __version__
    except Exception as exc:  # Keep tracebacks out of the renderer contract.
        response = _error("ENGINE_FAILURE", "The ShotLogFixer engine could not complete the request.", str(exc))
        response["version"] = __version__
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
