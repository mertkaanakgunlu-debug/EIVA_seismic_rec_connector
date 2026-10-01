"""Audit presentation only; canonical domain status/classification codes stay intact."""

import re

RECORD_LABELS = {
    "MATCHED": "Matched", "EIVA_ONLY": "EIVA only", "NO_SHOT": "Not recorded",
    "RECORDER_INVALID": "Invalid", "REVIEW": "Review",
}
GAP_LABELS = {
    "RECORDER_GAP_SHARED": "Shared gap",
    "RECORDER_GAP_WITH_EIVA_ONLY": "EIVA-only gap",
    "RECORDER_GAP_EXPLAINED_BY_NO_SHOT": "Explained by not-recorded shot",
    "RECORDER_GAP_MIXED": "Mixed",
    "RECORDER_GAP_AMBIGUOUS": "Needs review",
}


def format_diagnostic(text):
    labels = {**RECORD_LABELS, **GAP_LABELS, "INVALID": "Invalid", "VALID": "valid"}
    return re.sub(r"\b(?:RECORDER_GAP_[A-Z_]+|RECORDER_INVALID|EIVA_ONLY|NO_SHOT|MATCHED|REVIEW|INVALID|VALID)\b",
                  lambda match: labels.get(match[0], "Needs review"), text)
