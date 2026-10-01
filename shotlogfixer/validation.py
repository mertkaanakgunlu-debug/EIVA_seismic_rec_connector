"""Independent source-mapping and exact serialized engineering-pair validation."""

from collections import Counter
import math
import re
import statistics

from config import MAX_MATCH_DISTANCE_M, INVALID_COORDINATE
from .models import CorrectionPlan, EivaRecord, MatchResult, RecorderRecord, ValidationResult
from .parsers import classify_recorder_row, parse_eiva_text, parse_recorder_text


def _duplicates(values):
    return sorted(str(value) for value, count in Counter(values).items() if count > 1)


def _distances(result, pairs):
    distances = []
    for eiva, recorder in pairs:
        if recorder.source_x is None or recorder.source_y is None:
            result.invalid_rows_remaining += 1
            continue
        distance = math.hypot(eiva.easting_spark - recorder.source_x,
                              eiva.northing_spark - recorder.source_y)
        if not math.isfinite(distance):
            result.invalid_rows_remaining += 1
            continue
        distances.append(distance)
        if distance <= MAX_MATCH_DISTANCE_M:
            result.coordinate_pass_count += 1
        else:
            result.above_tolerance_count += 1
    if distances:
        result.max_distance_m = max(distances)
        result.mean_distance_m = statistics.mean(distances)
        result.median_distance_m = statistics.median(distances)


def validate_serialized(eiva_text: str, recorder_text: str) -> ValidationResult:
    result = ValidationResult(False)
    try:
        eiva = parse_eiva_text(eiva_text)
        recorder = parse_recorder_text(recorder_text)
    except (ValueError, IndexError) as exc:
        result.errors.append(f"Serialized candidate could not be parsed: {exc}")
        return result
    result.fixed_eiva_count, result.fixed_recorder_count = len(eiva), len(recorder)
    result.ffid_pair_count = min(len(eiva), len(recorder))
    eids, rids = [row.original_ffid for row in eiva], [row.ffid for row in recorder]
    result.ffid_match_count = sum(a == b for a, b in zip(eids, rids))
    result.duplicate_ffids = sorted(set(_duplicates(eids) + _duplicates(rids)))
    result.missing_ffids = list((Counter(rids) - Counter(eids)).elements())
    result.extra_ffids = list((Counter(eids) - Counter(rids)).elements())
    result.no_shot_rows_remaining = sum(classify_recorder_row(row) == "NO_SHOT" for row in recorder)
    result.invalid_rows_remaining = sum(classify_recorder_row(row) == "INVALID" for row in recorder)
    for row in eiva:
        values = {key.lower(): value for key, value in row.original_values_by_column.items()}
        for name in ("e(spark)", "n(spark)"):
            if not re.fullmatch(r"[+-]?\d+\.\d{2}", values[name].strip()):
                result.errors.append(f"EIVA line {row.source_line_number}: coordinates are not two decimals")
        if row.easting_spark == INVALID_COORDINATE or row.northing_spark == INVALID_COORDINATE:
            result.no_shot_rows_remaining += 1
    for row in recorder:
        for value in row.original_fields[1:3]:
            if not re.fullmatch(r"[+-]?\d+\.\d{2}", value):
                result.errors.append(f"Recorder line {row.source_line_number}: coordinates are not two decimals")
    _distances(result, zip(eiva, recorder))
    if not eiva or not recorder: result.errors.append("Engineering pair must contain valid shots")
    if len(eiva) != len(recorder): result.errors.append("Serialized row-count mismatch")
    if result.ffid_match_count != len(eiva): result.errors.append("Serialized row-by-row FFID mismatch")
    if result.duplicate_ffids: result.errors.append("Duplicate fixed FFIDs")
    if any(not value.strip() for value in eids + rids): result.errors.append("Missing FFID value")
    if result.missing_ffids or result.extra_ffids: result.errors.append("Missing or extra pair FFIDs")
    if result.no_shot_rows_remaining: result.errors.append("NO_SHOT remains in engineering pair")
    if result.invalid_rows_remaining: result.errors.append("Invalid coordinates remain in engineering pair")
    if result.coordinate_pass_count != len(eiva): result.errors.append("Serialized coordinates fail the 1.0 m tolerance")
    result.passed = not result.errors
    return result


def validate_candidates(source_eiva: list[EivaRecord], source_recorder: list[RecorderRecord],
                        plan: CorrectionPlan, eiva_text: str, recorder_text: str,
                        results: list[MatchResult]) -> ValidationResult:
    """Check original precision, coverage and provenance; then reparse final text."""
    classes = [classify_recorder_row(row) for row in source_recorder]
    valid_indices = [i for i, kind in enumerate(classes) if kind == "VALID"]
    result = ValidationResult(False, len(source_eiva), len(source_recorder), len(valid_indices),
                              classes.count("NO_SHOT"), classes.count("INVALID"))
    result.errors.extend(plan.blocking_reasons)
    if not plan.safe_to_build: result.errors.append("Correction plan is unsafe")
    if result.invalid_recorder_count: result.errors.append("Source contains INVALID recorder rows")
    result.unresolved_review_count = sum(row.status == "REVIEW" for row in results)
    if result.unresolved_review_count: result.errors.append("Unresolved REVIEW rows")
    if any(row.status == "NO_SHOT" and not row.eiva_record for row in results):
        result.errors.append("Unresolved NO_SHOT rows")

    keep = [action for action in plan.actions if action.action_type == "KEEP_AND_RENUMBER"]
    eis, ris = [a.eiva_source_index for a in keep], [a.recorder_source_index for a in keep]
    result.duplicate_source_mappings = _duplicates(eis) + _duplicates(ris)
    if result.duplicate_source_mappings: result.errors.append("Duplicate retained source mapping")
    all_eis = [a.eiva_source_index for a in plan.actions]
    if sorted(i for i in all_eis if isinstance(i, int)) != list(range(len(source_eiva))):
        result.errors.append("Plan does not cover each EIVA source row exactly once")
    if sorted(i for i in ris if isinstance(i, int)) != valid_indices:
        result.errors.append("Missing or extra valid recorder source mapping")
    result.non_monotonic_mapping_count = sum(
        not isinstance(a, int) or not isinstance(b, int) or b <= a
        for indices in (eis, ris) for a, b in zip(indices, indices[1:]))
    if result.non_monotonic_mapping_count: result.errors.append("Non-monotonic source mapping")
    source_pairs = []
    for action in keep:
        ei, ri = action.eiva_source_index, action.recorder_source_index
        if not isinstance(ei, int) or not isinstance(ri, int) or not (0 <= ei < len(source_eiva) and 0 <= ri < len(source_recorder)):
            result.errors.append("Source mapping index outside input")
            continue
        eiva, recorder = source_eiva[ei], source_recorder[ri]
        if action.original_eiva_ffid != eiva.original_ffid or action.target_ffid != recorder.ffid or action.recorder_ffid != recorder.ffid:
            result.errors.append("Action FFID provenance mismatch")
        if classes[ri] != "VALID": result.errors.append("Retained NO_SHOT or INVALID recorder row")
        source_pairs.append((eiva, recorder))
    _distances(result, source_pairs)
    if result.coordinate_pass_count != len(keep): result.errors.append("Original coordinates fail the 1.0 m tolerance")
    no_shot_ids = {row.ffid for row, kind in zip(source_recorder, classes) if kind == "NO_SHOT"}
    if any(row.ffid in no_shot_ids for _, row in source_pairs): result.errors.append("NO_SHOT FFID retained")

    serialized = validate_serialized(eiva_text, recorder_text)
    result.errors.extend(serialized.errors)
    result.fixed_eiva_count, result.fixed_recorder_count = serialized.fixed_eiva_count, serialized.fixed_recorder_count
    result.ffid_pair_count, result.ffid_match_count = serialized.ffid_pair_count, serialized.ffid_match_count
    result.duplicate_ffids = serialized.duplicate_ffids
    result.no_shot_rows_remaining += serialized.no_shot_rows_remaining
    result.invalid_rows_remaining += serialized.invalid_rows_remaining
    expected_ids = [row.ffid for row in source_recorder if classify_recorder_row(row) == "VALID"]
    try:
        fixed_eiva, fixed_recorder = parse_eiva_text(eiva_text), parse_recorder_text(recorder_text)
        actual_ids = [row.ffid for row in fixed_recorder]
        result.missing_ffids = list((Counter(expected_ids) - Counter(actual_ids)).elements())
        result.extra_ffids = list((Counter(actual_ids) - Counter(expected_ids)).elements())
        if [row.original_ffid for row in fixed_eiva] != expected_ids or actual_ids != expected_ids:
            result.errors.append("Engineering rows do not follow original valid recorder FFIDs/order")
        if len(fixed_eiva) != len(valid_indices) or len(fixed_recorder) != len(valid_indices) or len(keep) != len(valid_indices):
            result.errors.append("Fixed row count differs from expected VALID recorder count")
        # Independently check original navigation measurements and unrelated field values.
        for (original_eiva, original_recorder), output_eiva, output_recorder in zip(source_pairs, fixed_eiva, fixed_recorder):
            header = [key.lower() for key in original_eiva.original_values_by_column]
            targeted = {header.index(name) for name in ("ffid", "e(spark)", "n(spark)")}
            if len(original_eiva.original_fields) != len(output_eiva.original_fields) or any(
                original != fixed for i, (original, fixed) in enumerate(zip(original_eiva.original_fields, output_eiva.original_fields)) if i not in targeted):
                result.errors.append("Unrelated EIVA fields changed")
            values = {key.lower(): value.strip() for key, value in output_eiva.original_values_by_column.items()}
            if values["e(spark)"] != f"{original_eiva.easting_spark:.2f}" or values["n(spark)"] != f"{original_eiva.northing_spark:.2f}":
                result.errors.append("Original EIVA navigation coordinate was changed")
            if output_recorder.original_fields[:1] + output_recorder.original_fields[3:] != original_recorder.original_fields[:1] + original_recorder.original_fields[3:]:
                result.errors.append("Unrelated recorder fields or FFID changed")
            if output_recorder.original_fields[1:3] != [f"{original_recorder.source_x:.2f}", f"{original_recorder.source_y:.2f}"]:
                result.errors.append("Original recorder coordinates were changed")
    except (ValueError, IndexError, KeyError) as exc:
        result.errors.append(f"Candidate provenance check failed: {exc}")
    result.errors = list(dict.fromkeys(result.errors))
    result.passed = not result.errors
    return result
