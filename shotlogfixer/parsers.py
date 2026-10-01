import csv
import io
import math
from pathlib import Path

from .models import EivaRecord, RecorderRecord
from config import INVALID_COORDINATE

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def decode_source(raw: bytes) -> tuple[str, str]:
    # Preserve the presence or absence of the original UTF-8 BOM.
    for encoding in (("utf-8-sig",) if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252", "latin-1")):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file")


def _read(path: Path) -> str:
    return decode_source(path.read_bytes())[0]


def parse_eiva_text(text: str) -> list[EivaRecord]:
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        original_header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ValueError("EIVA file is empty")
    header = [h.lower() for h in original_header]
    required = {"ffid", "e(spark)", "n(spark)"}
    missing = required - set(header)
    if missing:
        raise ValueError(f"EIVA header missing columns: {', '.join(sorted(missing))}")
    if any(header.count(name) != 1 for name in required):
        raise ValueError("EIVA required column names must be unique")
    ix = {name: header.index(name) for name in required}
    lines = text.splitlines(keepends=True)
    previous_end = reader.line_num
    out = []
    try:
        for fields in reader:
            line, end = previous_end + 1, reader.line_num
            previous_end = end
            if not any(x.strip() for x in fields):
                continue
            try:
                out.append(EivaRecord(
                    line, fields[ix['ffid']].strip(), float(fields[ix['e(spark)']]),
                    float(fields[ix['n(spark)']]), fields, dict(zip(original_header, fields)),
                    ''.join(lines[line - 1:end]), end,
                ))
            except (IndexError, ValueError) as exc:
                raise ValueError(f"Malformed EIVA row at line {line}: {exc}") from exc
    except csv.Error as exc:
        raise ValueError(f"Malformed EIVA CSV at line {reader.line_num}: {exc}") from exc
    return out


def parse_eiva(path: str | Path) -> list[EivaRecord]:
    return parse_eiva_text(_read(Path(path)))


def classify_recorder_row(record: RecorderRecord) -> str:
    x, y = record.source_x, record.source_y
    if x is not None and y is not None and math.isfinite(x) and math.isfinite(y):
        if x == INVALID_COORDINATE and y == INVALID_COORDINATE:
            return "NO_SHOT"
        if x != INVALID_COORDINATE and y != INVALID_COORDINATE:
            return "VALID"
    return "INVALID"


def parse_recorder_text(text: str) -> list[RecorderRecord]:
    out = []
    header_seen = False
    header_fields: list[str] = []
    for line, raw in enumerate(text.splitlines(keepends=True), 1):
        if not raw.strip():
            continue
        parts = raw.split()
        if (not header_seen and [part.lower() for part in parts[:3]] == ["ffid", "sou_x", "sou_y"]):
            header_seen = True
            header_fields = parts
            continue
        def coordinate(index):
            try:
                return float(parts[index])
            except (IndexError, ValueError):
                return None
        row = RecorderRecord(line, parts[0], coordinate(1), coordinate(2), False,
                             parts, raw, header_fields=header_fields)
        row.classification = classify_recorder_row(row)
        row.coordinates_valid = row.classification == "VALID"
        out.append(row)
    return out


def parse_recorder(path: str | Path) -> list[RecorderRecord]:
    return parse_recorder_text(_read(Path(path)))
