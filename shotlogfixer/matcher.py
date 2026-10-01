import math
from collections import defaultdict

from .models import EivaRecord, RecorderRecord, MatchResult
from config import AMBIGUITY_MARGIN_M
from .analysis_parameters import AnalysisParameters


def _candidate_indices(eiva: list[EivaRecord], recorder: RecorderRecord, start: int, parameters: AnalysisParameters):
    candidates = []
    for index in range(start, len(eiva)):
        distance = math.hypot(eiva[index].easting_spark - recorder.source_x,
                              eiva[index].northing_spark - recorder.source_y)
        if distance <= parameters.match_tolerance_m:
            candidates.append((distance, index))
    return sorted(candidates)


def match_records(eiva: list[EivaRecord], recorder: list[RecorderRecord], parameters: AnalysisParameters | None = None) -> list[MatchResult]:
    """Match recorder coordinates monotonically and preserve uncertainty windows."""
    # Keep direct library compatibility while engine actions pass explicit
    # AnalysisParameters from the user-controlled boundary.
    parameters = parameters or AnalysisParameters(2.0)
    matched = {}
    eiva_status = {}
    recorder_events = defaultdict(list)
    cursor = 0
    uncertainty_start = None

    for rec in recorder:
        if not rec.coordinates_valid:
            recorder_events[cursor].append(MatchResult(
                None, rec, None, "RECORDER_INVALID",
                "Recorder coordinates are invalid (sentinel or non-finite)"))
            if uncertainty_start is None:
                uncertainty_start = cursor
            continue

        candidates = _candidate_indices(eiva, rec, cursor, parameters)
        if not candidates:
            recorder_events[cursor].append(MatchResult(
                None, rec, None, "REVIEW",
                "No plausible EIVA coordinate at or after sequence cursor"))
            if uncertainty_start is None:
                uncertainty_start = cursor
            continue

        distance, index = candidates[0]
        if len(candidates) > 1 and candidates[1][0] - distance < AMBIGUITY_MARGIN_M:
            recorder_events[cursor].append(MatchResult(
                None, rec, None, "REVIEW", "Ambiguous EIVA coordinate candidates"))
            if uncertainty_start is None:
                uncertainty_start = cursor
            continue

        if uncertainty_start is not None:
            for skipped in range(uncertainty_start, index):
                eiva_status[skipped] = (
                    "REVIEW", "Between recorder anomaly and next confirmed coordinate match")
            uncertainty_start = None
        else:
            for skipped in range(cursor, index):
                eiva_status[skipped] = (
                    "EIVA_ONLY", "No valid recorder coordinate counterpart")

        matched[index] = MatchResult(eiva[index], rec, distance, "MATCHED", "Coordinate match")
        cursor = index + 1

    if uncertainty_start is not None:
        for remaining in range(uncertainty_start, len(eiva)):
            eiva_status[remaining] = (
                "REVIEW", "Synchronization remained uncertain through end of recorder log")
    else:
        for remaining in range(cursor, len(eiva)):
            eiva_status[remaining] = (
                "EIVA_ONLY", "No valid recorder coordinate counterpart")

    output = []
    for index, record in enumerate(eiva):
        output.extend(recorder_events.pop(index, []))
        if index in matched:
            output.append(matched[index])
        else:
            status, diagnostic = eiva_status.get(
                index, ("EIVA_ONLY", "No valid recorder coordinate counterpart"))
            output.append(MatchResult(record, None, None, status, diagnostic))
    output.extend(recorder_events.pop(len(eiva), []))
    for events in recorder_events.values():
        output.extend(events)
    return output
