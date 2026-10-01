"""Coordinate-driven Recorder gap events. Source indices are zero based.

The right recorded anchor is never a missing position. Gap warnings and the
unexplained physical-position metric do not contribute to record issue counts.
Analysis visits consecutive VALID anchors and disjoint EIVA intervals once.
"""

import math

from .analysis_parameters import AnalysisParameters
from .models import RecorderGapEvent
from .parsers import classify_recorder_row


EXPLAINED = "RECORDER_GAP_EXPLAINED_BY_NO_SHOT"


def expected_slot(eiva, event):
    """Nearest unique intermediate lattice slot, with no enumeration of slots."""
    dx, dy = event.right_x - event.left_x, event.right_y - event.left_y
    # Normalize first to avoid squaring large coordinate spans.
    ux, uy = dx / event.distance_m, dy / event.distance_m
    projected = ((eiva.easting_spark - event.left_x) * ux
                 + (eiva.northing_spark - event.left_y) * uy)
    position = projected / event.distance_m * event.gap_span_steps
    if not math.isfinite(position):
        return None
    # A halfway point has no unique nearest slot; fail closed.
    if math.isclose(position - math.floor(position), .5, rel_tol=0, abs_tol=1e-12):
        return None
    slot = round(position)
    if not 1 <= slot < event.gap_span_steps:
        return None
    ratio = slot / event.gap_span_steps
    distance = math.hypot(eiva.easting_spark - (event.left_x + ratio * dx),
                          eiva.northing_spark - (event.left_y + ratio * dy))
    return slot if distance <= event.match_tolerance_m else None


def analyse_recorder_gaps(eiva, recorder, results, parameters: AnalysisParameters):
    classes = [classify_recorder_row(row) for row in recorder]
    valid = [i for i, kind in enumerate(classes) if kind == "VALID"]
    eindices = {id(row): i for i, row in enumerate(eiva)}
    rindices = {id(row): i for i, row in enumerate(recorder)}
    anchors = {rindices[id(row.recorder_record)]: eindices[id(row.eiva_record)]
               for row in results if row.status == "MATCHED" and row.eiva_record and row.recorder_record}
    by_eiva = {eindices[id(row.eiva_record)]: row for row in results if row.eiva_record}
    events = []
    for li, ri in zip(valid, valid[1:]):
        left, right = recorder[li], recorder[ri]
        distance = math.hypot(right.source_x - left.source_x, right.source_y - left.source_y)
        if distance <= 1.5 * parameters.shot_interval_m:
            continue
        ratio = distance / parameters.shot_interval_m
        if not math.isfinite(ratio):
            raise ValueError("Recorder gap geometry exceeds the supported numeric range")
        steps = round(ratio)
        if steps < 2:
            continue
        between = classes[li + 1:ri]
        ns, invalid = between.count("NO_SHOT"), between.count("INVALID")
        event = RecorderGapEvent(
            f"recorder-gap-{li + 1}-{ri + 1}", li, ri, left.ffid, right.ffid,
            left.source_x, left.source_y, right.source_x, right.source_y,
            distance, parameters.shot_interval_m, parameters.match_tolerance_m,
            steps, steps - 1, ns, invalid, max(0, steps - 1 - ns),
            anchors.get(li), anchors.get(ri))
        problems = []
        if invalid:
            problems.append("Generic INVALID Recorder rows between anchors")
        le, re = event.left_eiva_source_index, event.right_eiva_source_index
        if le is None or re is None or le >= re:
            problems.append("Missing or non-monotonic accepted EIVA anchors")
        else:
            event.intermediate_eiva_indices = list(range(le + 1, re))
            previous_slot = 0
            for ei in event.intermediate_eiva_indices:
                row = by_eiva[ei]
                if row.status == "EIVA_ONLY":
                    event.eiva_only_indices.append(ei)
                elif row.status == "NO_SHOT":
                    event.no_shot_eiva_indices.append(ei)
                else:
                    problems.append("Unresolved EIVA record inside Recorder gap")
                slot = expected_slot(eiva[ei], event)
                if slot is None or slot <= previous_slot:
                    problems.append("Off-slot, duplicate or non-monotonic EIVA slot assignment")
                else:
                    event.slot_assignments[ei] = slot
                    previous_slot = slot
        if len(event.no_shot_eiva_indices) != ns:
            problems.append("Explicit NO_SHOT association is unresolved")
        event.blocks_correction = bool(problems)
        if problems:
            event.classification = "RECORDER_GAP_AMBIGUOUS"
        elif ns and event.unexplained_missing_positions == 0:
            event.classification = EXPLAINED
        elif ns:
            event.classification = "RECORDER_GAP_MIXED"
        elif event.eiva_only_indices:
            event.classification = "RECORDER_GAP_WITH_EIVA_ONLY"
        else:
            event.classification = "RECORDER_GAP_SHARED"
        shared = max(0, event.unexplained_missing_positions - len(event.eiva_only_indices))
        event.diagnostic = (
            f"Recorder spatial gap {left.ffid} -> {right.ffid} spans approximately {steps} shot intervals; "
            f"{steps - 1} estimated missing intermediate positions; {ns} explicit NO_SHOT; "
            f"{event.unexplained_missing_positions} unexplained; {len(event.eiva_only_indices)} EIVA-only; "
            f"{shared} intermediate positions absent from both logs.")
        if problems:
            event.diagnostic += " " + "; ".join(dict.fromkeys(problems))
        for ei in event.intermediate_eiva_indices:
            row = by_eiva[ei]
            row.gap_event_ids.append(event.event_id)
            if row.status == "EIVA_ONLY":
                row.diagnostic = (f"Recorder spatial gap {left.ffid} -> {right.ffid}; "
                                  "EIVA position has no recorded shot counterpart. " + event.diagnostic)
        events.append(event)
    return events


def validate_gap_events(eiva, recorder, results, events, parameters):
    """Independent provenance/geometry checks, also repeated at the writer guard."""
    errors = []
    classes = [classify_recorder_row(row) for row in recorder]
    valid = [i for i, kind in enumerate(classes) if kind == "VALID"]
    expected_pairs = {(li, ri) for li, ri in zip(valid, valid[1:])
                      if math.hypot(recorder[ri].source_x - recorder[li].source_x,
                                    recorder[ri].source_y - recorder[li].source_y) > 1.5 * parameters.shot_interval_m}
    if {(g.left_recorder_source_index, g.right_recorder_source_index) for g in events} != expected_pairs or len(events) != len(expected_pairs):
        errors.append("Recorder gap coverage/anchor order mismatch")
    if len({g.event_id for g in events}) != len(events):
        errors.append("Duplicate Recorder gap event identifier")
    ei_by_id = {id(row): i for i, row in enumerate(eiva)}
    ri_by_id = {id(row): i for i, row in enumerate(recorder)}
    anchors = {ri_by_id[id(row.recorder_record)]: ei_by_id[id(row.eiva_record)]
               for row in results if row.status == "MATCHED" and row.eiva_record and row.recorder_record}
    by_eiva = {ei_by_id[id(row.eiva_record)]: row for row in results if row.eiva_record}
    for g in events:
        prefix = f"{g.event_id}: "
        li, ri = g.left_recorder_source_index, g.right_recorder_source_index
        if (li, ri) not in expected_pairs:
            errors.append(prefix + "Invalid source anchors")
            continue
        left, right = recorder[li], recorder[ri]
        distance = math.hypot(right.source_x - left.source_x, right.source_y - left.source_y)
        steps = round(distance / parameters.shot_interval_m)
        ns, invalid = classes[li + 1:ri].count("NO_SHOT"), classes[li + 1:ri].count("INVALID")
        if (g.left_recorder_ffid, g.right_recorder_ffid, g.left_x, g.left_y, g.right_x, g.right_y) != (left.ffid, right.ffid, left.source_x, left.source_y, right.source_x, right.source_y):
            errors.append(prefix + "Anchor coordinate/FFID provenance mismatch")
        if (g.distance_m, g.gap_span_steps, g.estimated_missing_positions, g.explicit_no_shot_count,
            g.invalid_between_count, g.unexplained_missing_positions, g.shot_interval_m, g.match_tolerance_m) != (
                distance, steps, steps - 1, ns, invalid, max(0, steps - 1 - ns), parameters.shot_interval_m, parameters.match_tolerance_m):
            errors.append(prefix + "Geometry/NO_SHOT accounting mismatch")
        le, re = anchors.get(li), anchors.get(ri)
        if le is None or re is None or le >= re or (g.left_eiva_source_index, g.right_eiva_source_index) != (le, re):
            errors.append(prefix + "Unresolved EIVA anchor mappings")
            continue
        expected_indices = list(range(le + 1, re))
        if g.intermediate_eiva_indices != expected_indices:
            errors.append(prefix + "EIVA interval coverage mismatch")
        eonly = [i for i in expected_indices if by_eiva[i].status == "EIVA_ONLY"]
        noshot = [i for i in expected_indices if by_eiva[i].status == "NO_SHOT"]
        if g.eiva_only_indices != eonly or g.no_shot_eiva_indices != noshot or len(noshot) != ns or len(eonly) + len(noshot) != len(expected_indices):
            errors.append(prefix + "EIVA attribution/NO_SHOT association mismatch")
        slots = []
        for ei in expected_indices:
            slot = expected_slot(eiva[ei], g)
            if slot is None or g.slot_assignments.get(ei) != slot:
                errors.append(prefix + "Expected-slot coordinate proof failed")
            else:
                slots.append(slot)
            if g.event_id not in by_eiva[ei].gap_event_ids:
                errors.append(prefix + "Missing record gap provenance")
        if set(g.slot_assignments) != set(expected_indices) or any(b <= a for a, b in zip(slots, slots[1:])):
            errors.append(prefix + "Duplicate/non-monotonic gap slots")
        classification = (EXPLAINED if ns and steps - 1 <= ns else "RECORDER_GAP_MIXED" if ns
                          else "RECORDER_GAP_WITH_EIVA_ONLY" if eonly else "RECORDER_GAP_SHARED")
        if g.blocks_correction or invalid or g.classification != classification:
            errors.append(prefix + "Unresolved ambiguous Recorder gap")
    return list(dict.fromkeys(errors))
