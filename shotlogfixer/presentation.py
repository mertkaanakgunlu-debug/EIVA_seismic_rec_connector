"""Audit presentation only; canonical status and code values stay intact in every payload."""

from .models import ASSIGNED, BLOCKED, INFO, INVALID_ROW, NO_SHOT_ROW, SEVERE, TARGET_ONLY, WARNING

ASSOCIATION_LABELS = {
    ASSIGNED: "Assigned", TARGET_ONLY: "Target-only", INVALID_ROW: "Invalid", NO_SHOT_ROW: "No shot", BLOCKED: "Blocked",
}
SEVERITY_LABELS = {None: "OK", INFO: "Note", WARNING: "Warning", SEVERE: "Severe"}
QC_LABELS = {
    "RECORDER_INVALID_ROW": "Recorder row invalid",
    "RECORDER_NO_SHOT_ROW": "Recorder no-shot row",
    "RECORDER_DUPLICATE_FFID": "Duplicate recorder FFID",
    "RECORDER_FFID_DISCONTINUITY": "Recorder FFID discontinuity",
    "RECORDER_DUPLICATE_COORDINATE": "Recorder duplicate coordinate",
    "RECORDER_POSITION_JUMP": "Recorder position jump",
    "RECORDER_POSITION_SPIKE": "Recorder position spike",
    "RECORDER_SPACING_IRREGULAR": "Recorder spacing irregular",
    "SHOT_INTERVAL_MISMATCH": "Shot interval mismatch",
    "TARGET_INVALID_ROW": "Target row invalid",
    "TARGET_ONLY": "Target-only row",
    "TARGET_ONLY_BLOCK": "Target-only block",
    "TARGET_POSITION_JUMP": "Target position jump",
    "TARGET_POSITION_SPIKE": "Target position spike",
    "TARGET_DUPLICATE_COORDINATE": "Target duplicate coordinate",
    "TARGET_SPACING_IRREGULAR": "Target spacing irregular",
    "TARGET_DUPLICATE_FFID": "Duplicate target FFID",
    "TARGET_FFID_DISCONTINUITY": "Target FFID discontinuity",
    "ASSOCIATION_DISTANCE_ELEVATED": "Elevated distance",
    "ASSOCIATION_DISTANCE_LARGE": "High distance",
    "ASSOCIATION_DISTANCE_SEVERE": "Severe distance",
    "ASSOCIATION_SEQUENCE_ONLY": "Placed by sequence",
    "ASSOCIATION_AMBIGUOUS": "Ambiguous",
    "ASSOCIATION_NEAREST_OVERRIDDEN": "Nearest row not used",
    "ASSOCIATION_RUN_DISPLACED": "Displaced run",
    "ASSOCIATION_BLOCKED": "Blocked",
}


def qc_label(code: str) -> str:
    return QC_LABELS.get(code, code.replace("_", " ").capitalize())
