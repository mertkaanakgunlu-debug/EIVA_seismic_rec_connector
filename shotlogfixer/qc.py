"""Small pure helpers for QC presentation and navigation."""

from .models import MatchResult

PROBLEM_STATUSES = {"EIVA_ONLY", "REVIEW", "RECORDER_INVALID"}


def problem_result_indices(results: list[MatchResult], status: str) -> list[int]:
    return [i for i, result in enumerate(results) if result.status == status]


def next_cycle(indices: list[int], current: int | None, step: int = 1) -> int | None:
    if not indices:
        return None
    if current not in indices:
        return indices[0] if step >= 0 else indices[-1]
    return indices[(indices.index(current) + step) % len(indices)]


def anomaly_event_count(results: list[MatchResult]) -> int:
    """Count contiguous problem regions in the acquisition-ordered result stream."""
    count = 0
    in_event = False
    for result in results:
        problem = result.status in PROBLEM_STATUSES
        if problem and not in_event:
            count += 1
        in_event = problem
    return count


def anomaly_frequency_per_1000(results: list[MatchResult], eiva_count: int) -> float:
    return anomaly_event_count(results) / eiva_count * 1000 if eiva_count else 0.0


def ffid_discontinuities(eiva_records) -> list[tuple[str, str]]:
    jumps = []
    for previous, current in zip(eiva_records, eiva_records[1:]):
        try:
            before, after = int(previous.original_ffid), int(current.original_ffid)
        except (TypeError, ValueError):
            continue
        if after - before != 1:
            jumps.append((previous.original_ffid, current.original_ffid))
    return jumps
