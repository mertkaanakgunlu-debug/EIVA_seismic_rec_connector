"""Stage A: normalise a parsed table into role-tagged ``SourceRecord`` objects.

This is the only place where an input's mapped FFID / X / Y columns are interpreted.  Rows that cannot
be interpreted are *kept* (with an explicit classification and reason) instead of aborting the whole
analysis: the sequence position of an unreadable row is still evidence, and QC reports it.
"""
from config import INVALID_COORDINATE
from .format_profiles import ROLES
from .models import INVALID, NO_SHOT, REFERENCE, TARGET, VALID, SourceRecord
from .profile_validation import finite
from .table_parser import parse_table


def classify_reference(ffid, x, y):
    """Return (classification, reason) for one reference row."""
    if x is None or y is None:
        return INVALID, "coordinate is missing or not a finite number"
    sentinels = (x == INVALID_COORDINATE) + (y == INVALID_COORDINATE)
    if sentinels == 1:
        return INVALID, "only one coordinate holds the no-shot sentinel"
    number = finite(ffid)
    if number is None or not number.is_integer():
        return INVALID, "FFID is not an integer"
    return (NO_SHOT, "coordinates hold the no-shot sentinel") if sentinels == 2 else (VALID, "")


def map_records(table, profile):
    role = REFERENCE if profile.workflow_role == "REFERENCE" else TARGET
    ffid_index, x_index, y_index = (profile.mapping[r] for r in ROLES[profile.input_type])
    columns = tuple(table.header or [f"Column {i + 1}" for i in range(table.column_count)])
    records = []
    for row_index, row in enumerate(table.rows):
        cells = tuple(row.cells)
        present = ffid_index < len(cells)
        ffid = cells[ffid_index].strip() if present else ""
        x = finite(cells[x_index]) if x_index < len(cells) else None
        y = finite(cells[y_index]) if y_index < len(cells) else None
        if role == REFERENCE:
            classification, reason = classify_reference(ffid, x, y)
        elif x is None or y is None:
            classification, reason = INVALID, "coordinate is missing or not a finite number"
        else:
            classification, reason = VALID, ""
        records.append(SourceRecord(role, row_index, row.source_line_number, row.source_end_line_number,
                                    row.raw_text, cells, ffid, x, y, classification, reason, present, columns))
    return records


def parse_canonical(text, profile):
    return map_records(parse_table(text, profile), profile)
