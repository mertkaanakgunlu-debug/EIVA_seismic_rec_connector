import math
from .models import EivaRecord, RecorderRecord, MatchResult
from config import MAX_MATCH_DISTANCE_M, AMBIGUITY_MARGIN_M

def match_records(eiva: list[EivaRecord], recorder: list[RecorderRecord]) -> list[MatchResult]:
    results = []; used = set(); cursor = 0; matched_eiva = set(); invalid_pending = False; review_indices = set()
    for rec in recorder:
        if not rec.coordinates_valid:
            results.append(MatchResult(None, rec, None, "RECORDER_INVALID", "Recorder coordinates equal invalid sentinel")); invalid_pending = True; continue
        candidates = []
        for i in range(cursor, len(eiva)):
            d = math.hypot(eiva[i].easting_spark-rec.source_x, eiva[i].northing_spark-rec.source_y)
            if d <= MAX_MATCH_DISTANCE_M: candidates.append((d, i))
        if not candidates:
            results.append(MatchResult(None, rec, None, "REVIEW", "No plausible EIVA coordinate at or after sequence cursor")); continue
        candidates.sort(); best, i = candidates[0]
        if len(candidates) > 1 and candidates[1][0] - best < AMBIGUITY_MARGIN_M:
            results.append(MatchResult(None, rec, None, "REVIEW", "Ambiguous EIVA coordinate candidates")); continue
        results.append(MatchResult(eiva[i], rec, best, "MATCHED", "Coordinate match")); used.add(i); matched_eiva.add(i); cursor = i + 1
        if invalid_pending:
            review_indices.add(max(0, i - 1))
            invalid_pending = False
    for i, record in enumerate(eiva):
        if i not in matched_eiva:
            status = "REVIEW" if i in review_indices else "EIVA_ONLY"
            reason = "Adjacent to invalid recorder event; manual review required" if status == "REVIEW" else "No valid recorder coordinate counterpart"
            results.append(MatchResult(record, None, None, status, reason))
    return results
