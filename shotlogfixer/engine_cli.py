"""Structured JSON boundary for the ShotLogFixer engine.

The Electron main process talks to this module over stdin/stdout.  Domain logic stays in the alignment, QC,
correction and report modules; this module only validates requests and serialises results.

Roles: the *reference* input is the authoritative recorder log; the *target* input is the EIVA/navigation log that is
corrected.  Requests use ``reference_*`` / ``target_*`` keys; the former ``recorder_*`` / ``eiva_*`` keys are accepted
as aliases.  The format-profile slots keep their stored names (RECORDER = reference, EIVA = target).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .analysis import Analysis, InputError, row_confidence, run_analysis
from .analysis_parameters import AnalysisConfiguration, AnalysisParameters
from .correction import CorrectionNotValidatedError, sha256_file
from .format_detection import detect_file
from .format_profiles import FormatProfile, INPUT_TYPE_FOR_ROLE, ProfileStore, builtin_profiles
from .models import ASSIGNED, INFO, INVALID, NO_SHOT, SEVERE, WARNING
from .profile_validation import validate_profile
from .qc import summarise
from .report import export_txt
from .table_parser import parse_table
from .version import __version__

REFERENCE_INPUT, TARGET_INPUT = INPUT_TYPE_FOR_ROLE["REFERENCE"], INPUT_TYPE_FOR_ROLE["TARGET"]


def _error(code: str, message: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    return payload


def _validate_file(value: Any, label: str) -> Path | dict[str, Any]:
    if isinstance(value, Path): value = str(value)
    if not isinstance(value, str) or not value.strip():
        return _error(f"MISSING_{label.upper()}_FILE", f"Select a {label} file.")
    path = Path(value).expanduser()
    if not path.exists():
        return _error("FILE_NOT_FOUND", f"The selected {label} file does not exist.", str(path))
    if not path.is_file():
        return _error("PATH_NOT_FILE", f"The selected {label} path is not a file.", str(path))
    return path


def _parameters(value: Any) -> AnalysisParameters | dict[str, Any]:
    if isinstance(value, str): value = value.replace(",", ".")
    try:
        return AnalysisParameters(value)
    except ValueError as exc:
        return _error("INVALID_SHOT_INTERVAL", "Enter a finite positive Shot Interval in metres.", str(exc))


def _resolve_profile(path, input_type, supplied=None):
    if supplied is not None:
        try: profile = FormatProfile.from_dict(supplied)
        except (ValueError, TypeError) as exc: return None, _error("INVALID_FORMAT_PROFILE", "The input format profile is invalid.", str(exc))
        if profile.input_type != input_type: return None, _error("INVALID_FORMAT_PROFILE", f"The profile is not for {input_type} input.")
        text = Path(path).read_bytes()
        from .source_reader import decode_source
        decoded, _ = decode_source(text, profile.structure.encoding)
    else:
        try:
            profile, _, _ = detect_file(path, input_type)
            from .source_reader import decode_source
            # Detection itself is bounded; once a profile is proposed, validate it
            # against the complete source before allowing analysis.
            decoded, _ = decode_source(Path(path).read_bytes(), profile.structure.encoding)
        except (OSError, ValueError) as exc: return None, _error("FORMAT_DETECTION_FAILED", "Unable to detect the input format.", str(exc))
    try:
        table = parse_table(decoded, profile)
        check = validate_profile(profile, table, require_confirmation=False)
    except ValueError as exc: return None, _error("FORMAT_NOT_READY", "The input format could not be validated.", str(exc))
    if not check["valid"]: return None, _error("FORMAT_NOT_READY", "The input format could not be validated.", " ".join(check["errors"]))
    return profile, None


def _format_payload(profile, header_columns=None):
    data = profile.as_dict()
    data["profile_hash"] = profile.profile_hash
    data["delimiter"] = profile.structure.delimiter
    data["header"] = profile.structure.header_mode
    data["confidence"] = profile.confidence
    data["input_type"] = profile.input_type
    data["header_columns"] = list(header_columns or [])
    return data


def _check_expected_hashes(reference, target, expected):
    if not expected: return None
    if (expected.get("reference", expected.get("recorder")) != sha256_file(reference)
            or expected.get("target", expected.get("eiva")) != sha256_file(target)):
        return _error("INPUT_CHANGED", "Input file changed — format and analysis must be revalidated.")
    return None


def _first(payload: dict, *names):
    for name in names:
        if payload.get(name) is not None:
            return payload[name]
    return None


def detect_format(path_value: Any, input_type: str):
    path = _validate_file(path_value, "reference" if input_type == REFERENCE_INPUT else "target")
    if isinstance(path, dict): return path
    try:
        profile, metadata, text = detect_file(path, input_type)
        from .source_reader import decode_source
        text, _ = decode_source(Path(path).read_bytes(), profile.structure.encoding)
        table = parse_table(text, profile)
        validation = validate_profile(profile, table, False)
    except (OSError, ValueError) as exc:
        return _error("FORMAT_DETECTION_FAILED", "Unable to inspect the selected input format.", str(exc))
    table_preview = parse_table(text, profile)
    rows = table_preview.rows
    def rows_at(mode):
        if mode == "first": return rows[:20]
        if mode == "last": return rows[-20:]
        if not rows: return []
        step = max(1, len(rows) // 20)
        return rows[::step][:20]
    previews = {mode: [{"line": r.source_line_number, "raw": r.raw_text, "cells": r.cells} for r in rows_at(mode)] for mode in ("first", "random", "last")}
    return {"ok": True, "profile": _format_payload(profile, table.header), "metadata": metadata, "validation": validation, "preview": previews,
            "columns": table_preview.header or [f"Column {index + 1}" for index in range(table_preview.column_count)]}


def preview_format(path_value: Any, input_type: str, profile_data=None):
    path = _validate_file(path_value, "reference" if input_type == REFERENCE_INPUT else "target")
    if isinstance(path, dict): return path
    profile, failure = _resolve_profile(path, input_type, profile_data)
    if failure: return failure
    try:
        from .source_reader import decode_source
        text, _ = decode_source(path.read_bytes(), profile.structure.encoding)
        table = parse_table(text, profile)
        validation = validate_profile(profile, table, require_confirmation=False)
    except (OSError, ValueError) as exc:
        return _error("FORMAT_PREVIEW_FAILED", "Unable to preview the selected format.", str(exc))
    rows = table.rows
    def sample(mode):
        if mode == "first": return rows[:20]
        if mode == "last": return rows[-20:]
        step = max(1, len(rows) // 20)
        return rows[::step][:20]
    return {"ok": True, "profile": _format_payload(profile, table.header), "validation": validation,
            "preview": {mode: [{"line": row.source_line_number, "raw": row.raw_text, "cells": row.cells} for row in sample(mode)] for mode in ("first", "random", "last")},
            "columns": table.header or [f"Column {index + 1}" for index in range(table.column_count)]}


def profiles_action(action, profile_data=None, name=None, profile_id=None):
    store = ProfileStore()
    try:
        if action == "list_profiles":
            return {"ok": True, "profiles": [_format_payload(p) for p in builtin_profiles() + store.load()]}
        if action == "delete_profile":
            store.delete(profile_id); return {"ok": True}
        if action == "save_profile":
            profile = FormatProfile.from_dict(profile_data)
            saved = store.save(profile, name, profile_id)
            return {"ok": True, "profile": _format_payload(saved)}
    except (OSError, ValueError, TypeError) as exc:
        return _error("PROFILE_OPERATION_FAILED", "Unable to update local format profiles.", str(exc))
    return _error("INVALID_PROFILE_ACTION", "Unsupported format profile action.")


# ------------------------------------------------------------------------------------------------------
# Reconciliation
# ------------------------------------------------------------------------------------------------------

def prepare_analysis(payload: dict, *, needs_hashes: bool = False):
    """Validate a reconciliation request and run the analysis.  Returns (Analysis, None) or (None, error)."""
    parameters = _parameters(payload.get("shot_interval_m"))
    if isinstance(parameters, dict): return None, parameters
    reference = _validate_file(_first(payload, "reference_path", "recorder_path"), "reference")
    if isinstance(reference, dict): return None, reference
    target = _validate_file(_first(payload, "target_path", "eiva_path"), "target")
    if isinstance(target, dict): return None, target
    if needs_hashes:
        changed = _check_expected_hashes(reference, target, payload.get("expected_hashes"))
        if changed: return None, changed
    reference_profile, failure = _resolve_profile(reference, REFERENCE_INPUT, _first(payload, "reference_profile", "recorder_profile"))
    if failure: return None, failure
    target_profile, failure = _resolve_profile(target, TARGET_INPUT, _first(payload, "target_profile", "eiva_profile"))
    if failure: return None, failure
    try:
        return run_analysis(reference, target, parameters, reference_profile, target_profile), None
    except InputError as exc:
        label = "reference" if exc.role == "REFERENCE" else "target"
        if exc.kind == "PERMISSION":
            return None, _error(f"{exc.role}_PERMISSION_DENIED", f"Unable to open the selected {label} file.", str(exc))
        return None, _error(f"INVALID_{exc.role}_FILE", f"Unable to parse the selected {label} file.", str(exc))
    except CorrectionNotValidatedError as exc:
        return None, _error("INPUT_CHANGED", "Input file changed — format and analysis must be revalidated.", str(exc))
    except (OSError, ValueError) as exc:
        return None, _error("ANALYSIS_FAILED", "Unable to reconcile the two files.", str(exc))


def _serialize_row(row, parameters) -> dict[str, Any]:
    ref, tgt, pair = row.reference, row.target, row.pair
    messages = [f.message for f in row.findings[:2]]
    return {
        "id": row.id,
        "acquisition_position": row.position,
        "association": row.association,
        "reference_ffid": ref.original_ffid if ref else None,
        "reference_line": ref.source_line_number if ref else None,
        "reference_x": ref.x if ref else None,
        "reference_y": ref.y if ref else None,
        "target_ffid": tgt.original_ffid if tgt else None,
        "target_line": tgt.source_line_number if tgt else None,
        "target_x": tgt.x if tgt else None,
        "target_y": tgt.y if tgt else None,
        "corrected_ffid": row.corrected_ffid,
        "distance_m": pair.distance_m if pair else None,
        "basis": pair.basis if pair else None,
        "confidence": row_confidence(row, parameters),
        "qc_severity": row.qc_severity or "OK",
        "qc_codes": list(dict.fromkeys(f.code for f in row.findings)),
        "diagnostic": " | ".join(messages),
        "target_values": tgt.values_by_column() if tgt else {},
    }


def _serialize_findings(analysis: Analysis) -> list[dict[str, Any]]:
    owner = {id(f): row.id for row in analysis.rows for f in row.findings}
    return [{"scope": f.scope, "code": f.code, "severity": f.severity, "message": f.message,
             "reference_row": f.reference_row, "target_row": f.target_row, "row_id": owner.get(id(f)),
             "metrics": f.metrics or {}} for f in analysis.findings]


def _summary(analysis: Analysis) -> dict[str, Any]:
    reference, target, plan, alignment = analysis.reference, analysis.target, analysis.plan, analysis.alignment
    qc = summarise(analysis.findings)["by_severity"]
    severities = [row.qc_severity for row in analysis.rows if row.association == ASSIGNED]
    return {
        "reference_rows": len(reference),
        "reference_valid": alignment.reference_valid,
        "reference_no_shot": sum(r.classification == NO_SHOT for r in reference),
        "reference_invalid": sum(r.classification == INVALID for r in reference),
        "target_rows": len(target),
        "target_invalid": sum(t.classification == INVALID for t in target),
        "assigned": len(alignment.associations),
        "target_only": plan.target_only_removed,
        "invalid_target_removed": plan.invalid_target_removed,
        "blocked": len(alignment.unplaced_reference_rows),
        "corrected_rows": plan.corrected_rows,
        "expected_rows": plan.expected_rows,
        "qc_info": qc.get(INFO, 0), "qc_warning": qc.get(WARNING, 0), "qc_severe": qc.get(SEVERE, 0),
        "assigned_with_warning": sum(s == WARNING for s in severities),
        "assigned_with_severe": sum(s == SEVERE for s in severities),
    }


def analyse_response(analysis: Analysis) -> dict[str, Any]:
    parameters, plan = analysis.parameters, analysis.plan
    target_headers = list(analysis.target[0].columns) if analysis.target else []
    reference_headers = list(analysis.reference[0].columns) if analysis.reference else []
    configuration = AnalysisConfiguration(parameters, analysis.reference_profile, analysis.target_profile)
    findings = _serialize_findings(analysis)
    ffid_jumps = [{"from": f["metrics"].get("from"), "to": f["metrics"].get("to"), "kind": f["metrics"].get("kind"), "row_id": f["row_id"]}
                  for f in findings if f["code"] == "RECORDER_FFID_DISCONTINUITY"]
    return {
        "ok": True,
        "summary": _summary(analysis),
        "parameters": parameters.as_dict(),
        "analysis_configuration": configuration.as_dict(),
        "correction": {
            "safe": plan.safe_to_build and analysis.validation.passed,
            "blockers": [{"code": b.code, "message": b.message} for b in plan.blockers],
            "assigned": plan.assigned,
            "target_only_removed": plan.target_only_removed,
            "invalid_target_removed": plan.invalid_target_removed,
            "corrected_rows": plan.corrected_rows,
            "expected_rows": plan.expected_rows,
            "direction": analysis.alignment.direction,
        },
        "validation": analysis.validation.as_dict(),
        "qc": {"summary": summarise(analysis.findings), "findings": findings, "ffid_jumps": ffid_jumps},
        "input_hashes": analysis.input_hashes,
        "input_formats": {"reference": _format_payload(analysis.reference_profile, reference_headers),
                          "target": _format_payload(analysis.target_profile, target_headers)},
        "target_headers": target_headers,
        "records": [_serialize_row(row, parameters) for row in analysis.rows],
    }


def analyse(payload: dict[str, Any]) -> dict[str, Any]:
    analysis, failure = prepare_analysis(payload)
    return failure if failure else analyse_response(analysis)


def save_corrected_target(payload: dict[str, Any]) -> dict[str, Any]:
    analysis, failure = prepare_analysis(payload, needs_hashes=True)
    if failure: return failure
    output_path = payload.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        return _error("MISSING_OUTPUT_PATH", "Choose a destination for the corrected target copy.")
    try:
        output = analysis.save_corrected(output_path, bool(payload.get("overwrite")))
    except FileExistsError as exc: return _error("OUTPUT_EXISTS", "The corrected output already exists; confirm overwrite.", str(exc))
    except (CorrectionNotValidatedError, OSError, ValueError) as exc: return _error("SAVE_BLOCKED", "The corrected copy was not written.", str(exc))
    return {"ok": True, "path": str(output), "rows": analysis.plan.corrected_rows, "validation": analysis.validation.as_dict(),
            "profile_hashes": {"reference": analysis.reference_profile.profile_hash, "target": analysis.target_profile.profile_hash},
            "raw_hashes_after": {"reference": sha256_file(analysis.reference_path), "target": sha256_file(analysis.target_path)}}


def export_qc(payload: dict[str, Any]) -> dict[str, Any]:
    analysis, failure = prepare_analysis(payload, needs_hashes=True)
    if failure: return failure
    output_path = payload.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        return _error("MISSING_EXPORT_PATH", "Choose a destination for the QC TXT.")
    output = Path(output_path).expanduser()
    reference_headers = list(analysis.reference[0].columns) if analysis.reference else []
    target_headers = list(analysis.target[0].columns) if analysis.target else []
    try:
        export_txt(output, analysis, {"reference": _format_payload(analysis.reference_profile, reference_headers),
                                      "target": _format_payload(analysis.target_profile, target_headers)})
    except PermissionError as exc:
        return _error("EXPORT_PERMISSION_DENIED", "Unable to write the QC TXT file.", str(exc))
    except (OSError, ValueError) as exc:
        return _error("EXPORT_FAILED", "Unable to export the QC TXT file.", str(exc))
    return {"ok": True, "path": str(output), "rows": len(analysis.rows), "parameters": analysis.parameters.as_dict(),
            "qc_findings": len(analysis.findings)}


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "analyse")
    if action == "detect_format":
        return detect_format(payload.get("path"), str(payload.get("input_type", "")).upper())
    if action == "preview_format":
        return preview_format(payload.get("path"), str(payload.get("input_type", "")).upper(), payload.get("profile"))
    if action in {"list_profiles", "save_profile", "delete_profile"}:
        return profiles_action(action, payload.get("profile"), payload.get("name"), payload.get("profile_id"))
    if action == "analyse":
        return analyse(payload)
    if action in {"export", "export_qc"}:
        return export_qc(payload)
    if action in {"save_corrected_target", "save_fixed_eiva"}:
        return save_corrected_target(payload)
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
