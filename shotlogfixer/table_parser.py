"""Generic table parsing shared by preview, canonical mapping and correction."""
from dataclasses import dataclass
import csv
import io
import re
from .format_profiles import FormatProfile


@dataclass(frozen=True)
class RawRow:
    source_line_number: int
    source_end_line_number: int
    raw_text: str
    cells: list[str]


@dataclass
class RawTable:
    header: list[str]
    rows: list[RawRow]
    skipped_lines: list[tuple[int, str]]
    column_count: int


def tokenize(raw, structure):
    if structure.delimiter == "whitespace": return raw.split()
    return next(csv.reader([raw], delimiter=structure.separator, quotechar=structure.quote_char, strict=True))


def parse_table(text, profile: FormatProfile):
    s = profile.structure
    lines = text.splitlines(keepends=True)
    filtered, numbers, skipped = [], [], []
    for n, raw in enumerate(lines, 1):
        if n <= s.skip_rows or not raw.strip() or any(raw.lstrip().startswith(p) for p in s.comment_prefixes):
            skipped.append((n, raw)); continue
        filtered.append(raw); numbers.append(n)
    rows, header = [], []
    if s.delimiter == "whitespace":
        entries = [(i, i + 1, raw.split()) for i, raw in enumerate(filtered)]
    else:
        reader = csv.reader(io.StringIO(''.join(filtered), newline=""), delimiter=s.separator, quotechar=s.quote_char, strict=True)
        entries = []
        end = 0
        try:
            for cells in reader:
                start, end = end, reader.line_num
                entries.append((start, end, cells))
        except csv.Error as exc: raise ValueError(f"Unable to tokenize table near source line {numbers[min(reader.line_num - 1, len(numbers)-1)]}: {exc}") from exc
    for ordinal, (start, end, cells) in enumerate(entries):
        if s.trim_whitespace: cells = [c.strip() for c in cells]
        if ordinal < s.header_row:
            skipped.extend((numbers[i], filtered[i]) for i in range(start, end)); continue
        if s.header_mode == "PRESENT" and ordinal == s.header_row:
            header = cells; continue
        rows.append(RawRow(numbers[start], numbers[end - 1], ''.join(lines[numbers[start]-1:numbers[end-1]]), cells))
    from collections import Counter
    count = len(header) if header else (Counter(len(r.cells) for r in rows).most_common(1)[0][0] if rows else 0)
    return RawTable(header, rows, skipped, count)


def replace_fields(raw, replacements, structure):
    """Replace targeted tokens, retaining separators, quoting and unrelated bytes."""
    if structure.delimiter == "whitespace":
        spans = list(re.finditer(r'\S+', raw))
        for index, value in sorted(replacements.items(), reverse=True):
            span = spans[index]
            raw = raw[:span.start()] + value + raw[span.end():]
        return raw
    tokens, start, quoted, i = [], 0, False, 0
    sep, quote = structure.separator, structure.quote_char
    while i < len(raw):
        if raw[i] == quote:
            if quoted and i + 1 < len(raw) and raw[i+1] == quote: i += 2; continue
            quoted = not quoted
        elif raw[i] == sep and not quoted:
            tokens.append(raw[start:i]); start = i + 1
        i += 1
    tokens.append(raw[start:])
    for index, value in replacements.items():
        old = tokens[index]
        prefix, suffix = old[:len(old)-len(old.lstrip())], old[len(old.rstrip()):]
        if old.strip().startswith(quote) or any(c in value for c in (sep, quote, '\n', '\r')):
            value = quote + value.replace(quote, quote * 2) + quote
        tokens[index] = prefix + value + suffix
    return sep.join(tokens)
