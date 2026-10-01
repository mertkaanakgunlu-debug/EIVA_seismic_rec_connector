import csv
import math
from pathlib import Path
from .models import EivaRecord, RecorderRecord
from config import INVALID_COORDINATE

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

def _read(path: Path) -> str:
    errors = []
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError as exc:
            errors.append(f"{enc}: {exc}")
    raise ValueError("Unable to decode file: " + "; ".join(errors))

def parse_eiva(path: str | Path) -> list[EivaRecord]:
    rows = list(csv.reader(_read(Path(path)).splitlines()))
    if not rows: raise ValueError("EIVA file is empty")
    original_header = [h.strip() for h in rows[0]]
    header = [h.lower() for h in original_header]
    required = {"ffid", "e(spark)", "n(spark)"}
    missing = required - set(header)
    if missing: raise ValueError(f"EIVA header missing columns: {', '.join(sorted(missing))}")
    ix = {name: header.index(name) for name in required}
    out = []
    for line, fields in enumerate(rows[1:], 2):
        if not any(x.strip() for x in fields): continue
        try:
            values = dict(zip(original_header, fields))
            out.append(EivaRecord(line, fields[ix['ffid']].strip(), float(fields[ix['e(spark)']]), float(fields[ix['n(spark)']]), fields, values))
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Malformed EIVA row at line {line}: {exc}") from exc
    return out

def parse_recorder(path: str | Path) -> list[RecorderRecord]:
    out = []
    header_seen = False
    for line, raw in enumerate(_read(Path(path)).splitlines(), 1):
        if not raw.strip(): continue
        parts = raw.split()
        if len(parts) < 3: raise ValueError(f"Malformed recorder row at line {line}")
        if (not header_seen and parts[0].strip().lower() == "ffid"
                and parts[1].strip().lower() == "sou_x"
                and parts[2].strip().lower() == "sou_y"):
            header_seen = True
            continue
        try: x, y = float(parts[1]), float(parts[2])
        except ValueError as exc: raise ValueError(f"Malformed recorder row at line {line}: {exc}") from exc
        valid = (math.isfinite(x) and math.isfinite(y)
                 and x != INVALID_COORDINATE and y != INVALID_COORDINATE)
        out.append(RecorderRecord(line, parts[0], x, y, valid))
    return out
