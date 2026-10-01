from .format_profiles import ROLES
from .models import EivaRecord, RecorderRecord
from .profile_validation import finite
from .parsers import classify_recorder_row
from .table_parser import parse_table


def map_records(table, profile):
    indices = [profile.mapping[r] for r in ROLES[profile.input_type]]
    names = table.header or [f"Column {i+1}" for i in range(table.column_count)]
    records = []
    for row in table.rows:
        def cell(i): return row.cells[i] if i < len(row.cells) else ""
        ffid, x, y = cell(indices[0]), finite(cell(indices[1])), finite(cell(indices[2]))
        if profile.input_type == "EIVA":
            if x is None or y is None: raise ValueError(f"Malformed EIVA coordinates at line {row.source_line_number}")
            records.append(EivaRecord(row.source_line_number, ffid, x, y, row.cells,
                                      dict(zip(names, row.cells)), row.raw_text, row.source_end_line_number))
        else:
            rec = RecorderRecord(row.source_line_number, ffid, x, y, False, row.cells, row.raw_text, header_fields=table.header)
            rec.source_end_line_number = row.source_end_line_number
            rec.classification = classify_recorder_row(rec)
            n = finite(ffid)
            if n is None or not n.is_integer(): rec.classification = "INVALID"; rec.source_x = None
            rec.coordinates_valid = rec.classification == "VALID"
            records.append(rec)
    return records


def parse_canonical(text, profile):
    return map_records(parse_table(text, profile), profile)
