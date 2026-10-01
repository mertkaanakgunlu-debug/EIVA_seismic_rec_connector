"""Bounded deterministic byte windows for inspection; full reads only for analysis."""
from collections import deque
from pathlib import Path
import hashlib


def decode_source(raw, encoding="AUTO"):
    choices = (encoding,) if encoding != "AUTO" else (("utf-8-sig",) if raw.startswith(b'\xef\xbb\xbf') else ("utf-8", "cp1252", "latin-1"))
    for candidate in choices:
        try: return raw.decode(candidate), candidate
        except UnicodeDecodeError: continue
    raise ValueError("Unable to decode source using selected encoding")


def source_signature(path):
    path = Path(path)
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def sample_source(path, encoding="AUTO", window=65536):
    path = Path(path)
    before = source_signature(path)
    size = before["size"]
    chunks = []
    with path.open("rb") as stream:
        for offset in sorted(set((0, max(0, size // 2 - window // 2), max(0, size - window)))):
            stream.seek(offset)
            raw = stream.read(window)
            if offset:
                cut = raw.find(b'\n')
                raw = raw[cut + 1:] if cut >= 0 else b''
            if offset + window < size:
                raw = raw[:raw.rfind(b'\n') + 1]
            chunks.append((offset, raw))
    # Inspect all bounded windows for UTF-8 validity, including the file tail.
    _, resolved = decode_source(b''.join(raw for _, raw in chunks), encoding)
    groups = []
    previous_end = -1
    for offset, raw in chunks:
        # Adjacent bounded windows can overlap on medium-sized files.  Keep
        # each byte range once so sampled rows never inflate validation counts
        # or bias delimiter/header scores.
        if offset < previous_end:
            continue
        text, _ = decode_source(raw, resolved)
        rows = []
        for i, line in enumerate(text.splitlines(keepends=True), 1):
            rows.append((i if offset == 0 else None, line))
        groups.append(rows)
        previous_end = offset + len(raw)
    if source_signature(path) != before: raise ValueError("Input file changed — format must be revalidated")
    return groups, resolved, before
