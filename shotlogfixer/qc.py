"""QC findings: what looks unusual and deserves a human look.

QC is independent of correction.  It reads the records and the alignment and reports observations; nothing here can
change which target row a reference record is associated with, whether a reference record exists, or whether a
corrected copy can be written.  (Correction blockers are a separate concept, see ``correction.py``.)

Scopes
    RECORDER     the authoritative reference input
    TARGET       the input being corrected
    ASSOCIATION  the relationship between an associated reference record and its target row
"""

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
import math
from statistics import median
from typing import Optional, Sequence

from .alignment import AlignmentResult
from .models import INFO, INVALID, NO_SHOT, SEVERE, SEVERITY_ORDER, WARNING, SourceRecord
from .profile_validation import finite

RECORDER, TARGET_SCOPE, ASSOCIATION = "RECORDER", "TARGET", "ASSOCIATION"
NEAREST_WINDOW = 6            # target rows either side searched for a closer row than the assigned one
RUN_MIN_ROWS = 10             # overridden associations that form one displacement finding
RUN_MAX_GAP = 8               # consecutive unflagged records tolerated inside one run (noise at the 0.5 m level)
IRREGULAR_SPACING_CAP = 200   # more irregular-spacing observations than this are summarised in one finding
TARGET_ONLY_BLOCK_ROWS = 3


@dataclass(frozen=True, slots=True)
class Finding:
    scope: str
    code: str
    severity: str
    message: str
    reference_row: Optional[int] = None     # SourceRecord.row_index of the reference record concerned
    target_row: Optional[int] = None        # SourceRecord.row_index of the target row concerned
    metrics: Optional[dict] = None


def worst_severity(findings: Sequence[Finding]) -> Optional[str]:
    return max((f.severity for f in findings), key=SEVERITY_ORDER.get, default=None)


def _ffid_number(record: SourceRecord) -> Optional[int]:
    value = finite(record.original_ffid)
    return int(value) if value is not None and value.is_integer() else None


def _dist(a: SourceRecord, b: SourceRecord) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _row_kwargs(record: SourceRecord) -> dict:
    return {"reference_row": record.row_index} if record.role == "REFERENCE" else {"target_row": record.row_index}


# ------------------------------------------------------------------------------------------------------
# Generic per-input geometry: position steps, spikes, duplicates, spacing
# ------------------------------------------------------------------------------------------------------

def _position_findings(scope: str, rows: Sequence[SourceRecord], params, *, strict_duplicates: bool) -> list[Finding]:
    """Findings about consecutive positioned records of one input, in file order."""
    prefix = "RECORDER" if scope == RECORDER else "TARGET"
    who = "Recorder" if scope == RECORDER else "Target"
    interval, jump, severe_jump = params.shot_interval_m, params.jump_distance_m, params.severe_jump_distance_m
    steps = [_dist(a, b) for a, b in zip(rows, rows[1:])]
    findings, irregular = [], []
    k = 1
    while k < len(rows):
        step_in = steps[k - 1]
        row = rows[k]
        if step_in >= jump:
            step_out = steps[k] if k + 1 < len(rows) else None
            chord = _dist(rows[k - 1], rows[k + 1]) if step_out is not None else None
            if step_out is not None and step_out >= jump and chord < 0.5 * min(step_in, step_out):
                peak = max(step_in, step_out)
                findings.append(Finding(scope, f"{prefix}_POSITION_SPIKE", SEVERE if peak >= severe_jump else WARNING,
                                        f"{who} position at line {row.source_line_number} (FFID {row.original_ffid}) is displaced "
                                        f"{peak:.1f} m from its neighbours and returns to the track.",
                                        metrics={"distance_m": peak, "step_in_m": step_in, "step_out_m": step_out}, **_row_kwargs(row)))
                k += 2          # the return step belongs to the same spike
                continue
            findings.append(Finding(scope, f"{prefix}_POSITION_JUMP", SEVERE if step_in >= severe_jump else WARNING,
                                    f"{who} position jumps {step_in:.1f} m ({step_in / interval:.0f} shot intervals) between FFID "
                                    f"{rows[k - 1].original_ffid} and FFID {row.original_ffid} (line {row.source_line_number}).",
                                    metrics={"distance_m": step_in, "intervals": step_in / interval}, **_row_kwargs(row)))
        elif step_in <= 1e-9:
            findings.append(Finding(scope, f"{prefix}_DUPLICATE_COORDINATE", WARNING if strict_duplicates else INFO,
                                    f"{who} FFID {row.original_ffid} (line {row.source_line_number}) repeats the coordinate of the previous record.",
                                    metrics={"distance_m": step_in}, **_row_kwargs(row)))
        elif step_in < 0.5 * interval or step_in > 1.5 * interval:
            irregular.append((row, step_in))
        k += 1
    if len(irregular) <= IRREGULAR_SPACING_CAP:
        for row, step in irregular:
            findings.append(Finding(scope, f"{prefix}_SPACING_IRREGULAR", INFO,
                                    f"{who} spacing before FFID {row.original_ffid} is {step:.2f} m against a {interval:g} m shot interval.",
                                    metrics={"distance_m": step, "intervals": step / interval}, **_row_kwargs(row)))
    elif irregular:
        row = irregular[0][0]
        findings.append(Finding(scope, f"{prefix}_SPACING_IRREGULAR", WARNING,
                                f"{len(irregular)} {who.lower()} spacings fall outside half to one and a half shot intervals "
                                f"({interval:g} m); check the entered shot interval.", metrics={"count": len(irregular)}, **_row_kwargs(row)))
    return findings


def _ffid_findings(scope: str, rows: Sequence[SourceRecord], *, authoritative: bool) -> list[Finding]:
    prefix = "RECORDER" if scope == RECORDER else "TARGET"
    findings, seen = [], {}
    numbered = [(r, _ffid_number(r)) for r in rows]
    for record, number in numbered:
        if number is None:
            continue
        if number in seen:
            first = seen[number]
            findings.append(Finding(scope, f"{prefix}_DUPLICATE_FFID", WARNING if authoritative else INFO,
                                    f"FFID {number} appears again at line {record.source_line_number} (first at line {first.source_line_number}).",
                                    metrics={"ffid": number, "first_line": first.source_line_number}, **_row_kwargs(record)))
        else:
            seen[number] = record
    for (a, na), (b, nb) in zip(numbered, numbered[1:]):
        if na is None or nb is None or nb - na in (0, 1):
            continue                                  # equal FFIDs are reported as duplicates
        if nb > na:
            missing = nb - na - 1
            severity = INFO if missing == 1 or not authoritative else WARNING
            message, kind = f"FFID jumps from {na} to {nb} ({missing} missing).", "GAP"
        else:
            severity, message, kind = (WARNING if authoritative else INFO), f"FFID decreases from {na} to {nb}.", "REVERSAL"
        if not authoritative:
            message += " (original target FFIDs are diagnostics only)"
        findings.append(Finding(scope, f"{prefix}_FFID_DISCONTINUITY", severity, message,
                                metrics={"from": na, "to": nb, "kind": kind}, **_row_kwargs(b)))
    return findings


# ------------------------------------------------------------------------------------------------------
# Reference (recorder) QC
# ------------------------------------------------------------------------------------------------------

def _reference_findings(reference: Sequence[SourceRecord], params) -> list[Finding]:
    findings, valid = [], []
    for r in reference:
        if r.classification == INVALID:
            findings.append(Finding(RECORDER, "RECORDER_INVALID_ROW", WARNING,
                                    f"Recorder row at line {r.source_line_number} cannot be interpreted: {r.invalid_reason}.",
                                    reference_row=r.row_index))
        elif r.classification == NO_SHOT:
            findings.append(Finding(RECORDER, "RECORDER_NO_SHOT_ROW", INFO,
                                    f"Recorder FFID {r.original_ffid} (line {r.source_line_number}) is marked 'no shot' by its sentinel "
                                    "coordinates; it is not treated as a recorded shot.", reference_row=r.row_index))
        else:
            valid.append(r)
    findings += _ffid_findings(RECORDER, valid, authoritative=True)
    findings += _position_findings(RECORDER, valid, params, strict_duplicates=True)
    regular = [_dist(a, b) for a, b in zip(valid, valid[1:])]
    regular = [d for d in regular if 0 < d < params.jump_distance_m]
    if len(regular) >= 10:
        typical = median(regular)
        if not 0.7 <= typical / params.shot_interval_m <= 1.4:
            findings.append(Finding(RECORDER, "SHOT_INTERVAL_MISMATCH", WARNING,
                                    f"The entered shot interval ({params.shot_interval_m:g} m) differs from the median recorder spacing "
                                    f"({typical:.3f} m); distance bands in this report may be misleading.",
                                    metrics={"entered_m": params.shot_interval_m, "median_spacing_m": typical}))
    return findings


# ------------------------------------------------------------------------------------------------------
# Target (EIVA) QC
# ------------------------------------------------------------------------------------------------------

def _target_findings(target: Sequence[SourceRecord], reference: Sequence[SourceRecord], alignment: AlignmentResult, params) -> list[Finding]:
    findings = []
    positioned = [t for t in target if t.has_position]
    findings += _position_findings(TARGET_SCOPE, positioned, params, strict_duplicates=False)
    findings += _ffid_findings(TARGET_SCOPE, [t for t in target if t.ffid_cell_present], authoritative=False)
    ffid_counts = Counter(t.original_ffid for t in target)
    for t in target:
        assigned = t.row_index in alignment.by_target
        if t.classification == INVALID:
            outcome = ("It keeps its place in the sequence and was assigned by sequence continuity." if assigned
                       else "It is not assigned and is removed from the corrected copy.")
            findings.append(Finding(TARGET_SCOPE, "TARGET_INVALID_ROW", WARNING,
                                    f"Target row at line {t.source_line_number} cannot be interpreted: {t.invalid_reason}. {outcome}",
                                    target_row=t.row_index))
    # Target rows with no reference record, grouped into runs for context.
    run = []

    def close(run, previous_ref, next_ref):
        for t in run:
            if t.classification == INVALID:
                continue
            context = _target_only_context(t, previous_ref, next_ref, reference, ffid_counts)
            findings.append(Finding(TARGET_SCOPE, "TARGET_ONLY", INFO, context[0], target_row=t.row_index, metrics=context[1]))
        if len(run) >= TARGET_ONLY_BLOCK_ROWS:
            findings.append(Finding(TARGET_SCOPE, "TARGET_ONLY_BLOCK", WARNING,
                                    f"{len(run)} consecutive target rows (from line {run[0].source_line_number}) have no recorder record.",
                                    target_row=run[0].row_index, metrics={"rows": len(run)}))

    previous_ref = None
    for t in target:
        pair = alignment.by_target.get(t.row_index)
        if pair is None:
            run.append(t)
            continue
        if run:
            close(run, previous_ref, reference[pair.reference_row])
            run = []
        previous_ref = reference[pair.reference_row]
    if run:
        close(run, previous_ref, None)
    return findings


def _target_only_context(t: SourceRecord, previous_ref, next_ref, reference, ffid_counts):
    before = f"recorder FFID {previous_ref.original_ffid}" if previous_ref else "the start of the recorder log"
    after = f"recorder FFID {next_ref.original_ffid}" if next_ref else "the end of the recorder log"
    hints = []
    low = previous_ref.row_index + 1 if previous_ref else 0
    high = next_ref.row_index if next_ref else len(reference)
    no_shots = [r for r in reference[low:high] if r.classification == NO_SHOT]
    if no_shots:
        hints.append(f"{len(no_shots)} recorder no-shot row(s) lie in the same gap")
    if ffid_counts[t.original_ffid] > 1:
        hints.append(f"its original FFID {t.original_ffid} is used by another target row")
    message = (f"Target row at line {t.source_line_number} (original FFID {t.original_ffid}) has no recorder record between {before} and {after}; "
               "it is removed from the corrected copy" + (f" ({'; '.join(hints)})." if hints else "."))
    return message, {"previous_reference_ffid": previous_ref.original_ffid if previous_ref else None,
                     "next_reference_ffid": next_ref.original_ffid if next_ref else None, "no_shot_rows": len(no_shots)}


# ------------------------------------------------------------------------------------------------------
# Association QC
# ------------------------------------------------------------------------------------------------------

def distance_band(distance: Optional[float], params) -> str:
    if distance is None:
        return "UNKNOWN"
    if distance <= params.normal_distance_m:
        return "NORMAL"
    if distance <= params.elevated_distance_m:
        return "ELEVATED"
    return "LARGE" if distance <= params.severe_distance_m else "SEVERE"


def association_confidence(association, params) -> str:
    band = distance_band(association.distance_m, params)
    if association.basis == "SEQUENCE" or band in ("LARGE", "SEVERE", "UNKNOWN"):
        return "LOW"
    return "MEDIUM" if band == "ELEVATED" or association.ambiguous else "HIGH"


def _association_findings(reference, target, alignment: AlignmentResult, params) -> list[Finding]:
    findings, flags, details = [], [], []
    for a in alignment.associations:
        ref, tgt = reference[a.reference_row], target[a.target_row]
        where = {"reference_row": a.reference_row, "target_row": a.target_row}
        band = distance_band(a.distance_m, params)
        shown = f"{a.distance_m:.2f} m" if a.distance_m is not None else "unknown"
        if band == "ELEVATED":
            findings.append(Finding(ASSOCIATION, "ASSOCIATION_DISTANCE_ELEVATED", INFO,
                                    f"Recorder FFID {ref.original_ffid} is {shown} from its target row (normal is up to "
                                    f"{params.normal_distance_m:g} m).", metrics={"distance_m": a.distance_m}, **where))
        elif band == "LARGE":
            findings.append(Finding(ASSOCIATION, "ASSOCIATION_DISTANCE_LARGE", WARNING,
                                    f"Recorder FFID {ref.original_ffid} is {shown} from its target row (more than one shot interval).",
                                    metrics={"distance_m": a.distance_m}, **where))
        elif band == "SEVERE":
            findings.append(Finding(ASSOCIATION, "ASSOCIATION_DISTANCE_SEVERE", SEVERE,
                                    f"Recorder FFID {ref.original_ffid} is {shown} from its target row "
                                    f"(more than {params.severe_distance_m:g} m); inspect the recorder coordinate.",
                                    metrics={"distance_m": a.distance_m}, **where))
        if a.basis == "SEQUENCE":
            reason = ("the target row has no usable position" if a.distance_m is None
                      else "the spatial distance is beyond the range in which it can rank candidates")
            findings.append(Finding(ASSOCIATION, "ASSOCIATION_SEQUENCE_ONLY", WARNING,
                                    f"Recorder FFID {ref.original_ffid} was placed by acquisition-sequence continuity because {reason}.",
                                    metrics={"distance_m": a.distance_m}, **where))
        if a.ambiguous:
            options = ", ".join(str(target[j].source_line_number) for j in a.alternative_target_rows)
            findings.append(Finding(ASSOCIATION, "ASSOCIATION_AMBIGUOUS", WARNING,
                                    f"Recorder FFID {ref.original_ffid} could equally be placed on other target rows (line {options}); "
                                    "the closest fit that keeps acquisition order was chosen (exact ties go to the earliest row).",
                                    metrics={"alternative_target_rows": list(a.alternative_target_rows)}, **where))
        # Is a much closer target row sitting next door while this one went elsewhere?
        direction, nearest = 0, None
        if a.distance_m is not None and a.distance_m > params.normal_distance_m and ref.has_position:
            low, high = max(0, a.target_row - NEAREST_WINDOW), min(len(target), a.target_row + NEAREST_WINDOW + 1)
            candidates = [(math.hypot(ref.x - t.x, ref.y - t.y), t.row_index) for t in target[low:high]
                          if t.has_position and t.row_index != a.target_row]
            if candidates:
                nearest = min(candidates)
                if nearest[0] <= 0.5 * a.distance_m:
                    direction = 1 if nearest[1] > a.target_row else -1
                    findings.append(Finding(ASSOCIATION, "ASSOCIATION_NEAREST_OVERRIDDEN", INFO,
                                            f"Recorder FFID {ref.original_ffid}: the spatially nearest target row (line "
                                            f"{target[nearest[1]].source_line_number}, {nearest[0]:.2f} m) was not used; sequence order and "
                                            "one-to-one assignment resolved it.",
                                            metrics={"nearest_distance_m": nearest[0], "assigned_distance_m": a.distance_m}, **where))
        flags.append(direction)
        details.append((a, nearest))
    for start, end, direction, count in _runs(flags):
        members = [k for k in range(start, end + 1) if flags[k] == direction]
        first, last = details[members[0]][0], details[members[-1]][0]
        assigned = [details[k][0].distance_m for k in members]
        nearest = [details[k][1][0] for k in members]
        findings.append(Finding(ASSOCIATION, "ASSOCIATION_RUN_DISPLACED", WARNING,
                                f"From recorder FFID {reference[first.reference_row].original_ffid} to FFID "
                                f"{reference[last.reference_row].original_ffid} ({count} records) the assigned target row is consistently "
                                f"one place {'before' if direction > 0 else 'after'} the spatially nearest row (median distance "
                                f"{median(assigned):.2f} m versus {median(nearest):.2f} m): the two logs may be offset by one shot here.",
                                reference_row=first.reference_row, target_row=first.target_row,
                                metrics={"records": count, "last_reference_row": last.reference_row,
                                         "median_assigned_distance_m": median(assigned), "median_nearest_distance_m": median(nearest)}))
    findings += _unplaced_findings(reference, target, alignment, params)
    return findings


def _unplaced_findings(reference, target, alignment: AlignmentResult, params) -> list[Finding]:
    """A valid recorder record with no target row is a real shot the target log lacks (or cannot hold in order)."""
    findings = []
    assigned = [r.row_index for r in reference if r.row_index in alignment.by_reference]
    for row in alignment.unplaced_reference_rows:
        r, detail = reference[row], alignment.unplaced.get(row)
        subject = f"Recorder FFID {r.original_ffid} (line {r.source_line_number}) has no target row"
        if len(target) < alignment.reference_valid:
            reason = f"the target has {len(target):,} rows but the recorder has {alignment.reference_valid:,} valid records."
        else:
            reason = _unplaced_reason(r, detail, reference, target, alignment, params, assigned)
        metrics = {"nearest_target_row": detail.nearest_target_row if detail else None,
                   "nearest_distance_m": detail.nearest_distance_m if detail else None,
                   "shift_records": detail.shift_records if detail else None,
                   "shift_cost_m": detail.shift_cost_m if detail else None}
        findings.append(Finding(ASSOCIATION, "ASSOCIATION_BLOCKED", SEVERE, f"{subject}: {reason}", reference_row=row, metrics=metrics))
    return findings


def _unplaced_reason(record, detail, reference, target, alignment, params, assigned) -> str:
    at = bisect_left(assigned, record.row_index)          # ``assigned`` is in reference order and excludes this record
    previous = assigned[at - 1] if at else None
    following = assigned[at] if at < len(assigned) else None
    neighbours = ("between recorder FFID {} and FFID {}".format(reference[previous].original_ffid, reference[following].original_ffid)
                  if previous is not None and following is not None else
                  f"after recorder FFID {reference[previous].original_ffid}" if previous is not None else
                  f"before recorder FFID {reference[following].original_ffid}" if following is not None else "anywhere")
    nearest = detail.nearest_target_row if detail else None
    if nearest is None:
        why = f"no target row lies within {params.alignment_cap_m:g} m of its coordinate and no free target row lies {neighbours}"
    else:
        near = target[nearest]
        holder = alignment.by_target.get(nearest)
        owner = ""
        if holder is not None:
            fit = f", {holder.distance_m:.2f} m" if holder.distance_m is not None else ""
            owner = f" belongs to recorder FFID {reference[holder.reference_row].original_ffid} (it fits it better{fit})"
        owner = owner or " lies outside the rows that acquisition order allows it"
        why = (f"its nearest target row (line {near.source_line_number}, {detail.nearest_distance_m:.2f} m){owner} "
               f"and no free target row lies {neighbours}")
    if detail is None or detail.shift_records is None:
        return why + "."
    side = "later" if detail.shift_side == "AFTER" else "earlier"
    which = "next" if detail.shift_side == "AFTER" else "previous"
    end = target[detail.shift_end_row]
    return (f"{why}. Making room would move the {which} {detail.shift_records:,} recorder records one target row {side} "
            f"(to the unused row at line {end.source_line_number}), adding {detail.shift_cost_m:,.0f} m of total distance to their "
            "associations, so it is left unassigned.")


def _runs(flags, min_rows=RUN_MIN_ROWS, max_gap=RUN_MAX_GAP):
    """Runs of consecutive same-direction flags (tolerating short interruptions): (start, end, direction, flagged)."""
    runs, i, n = [], 0, len(flags)
    while i < n:
        if flags[i] == 0:
            i += 1
            continue
        direction, last, gap, j = flags[i], i, 0, i + 1
        while j < n:
            if flags[j] == direction:
                last, gap = j, 0
            elif flags[j] == 0:
                gap += 1
                if gap > max_gap:
                    break
            else:
                break
            j += 1
        count = sum(1 for k in range(i, last + 1) if flags[k] == direction)
        if count >= min_rows:
            runs.append((i, last, direction, count))
        i = last + 1
    return runs


# ------------------------------------------------------------------------------------------------------

def run_qc(reference: Sequence[SourceRecord], target: Sequence[SourceRecord], alignment: AlignmentResult, params) -> list[Finding]:
    findings = _reference_findings(reference, params)
    findings += _target_findings(target, reference, alignment, params)
    findings += _association_findings(reference, target, alignment, params)
    return findings


def summarise(findings: Sequence[Finding]) -> dict:
    return {"total": len(findings),
            "by_severity": dict(Counter(f.severity for f in findings)),
            "by_scope": dict(Counter(f.scope for f in findings)),
            "by_code": dict(sorted(Counter(f.code for f in findings).items()))}
