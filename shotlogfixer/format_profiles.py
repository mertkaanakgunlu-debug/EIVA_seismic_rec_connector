"""Versioned offline input contracts. Column indices are zero based."""
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import uuid

ROLES = {"EIVA": ("FFID", "EIVA_EASTING", "EIVA_NORTHING"),
         "RECORDER": ("FFID", "RECORDER_X", "RECORDER_Y")}
DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|", "whitespace": None}


@dataclass(frozen=True)
class Structure:
    delimiter: str = "comma"
    header_mode: str = "PRESENT"
    header_row: int = 0
    skip_rows: int = 0
    encoding: str = "AUTO"
    quote_char: str = '"'
    trim_whitespace: bool = True
    comment_prefixes: tuple[str, ...] = ("#", "%", "//")

    @property
    def separator(self):
        return DELIMITERS.get(self.delimiter, self.delimiter)


@dataclass(frozen=True)
class FormatProfile:
    id: str
    name: str
    input_type: str
    structure: Structure
    column_mapping: tuple[tuple[str, int], ...]
    source: str = "DETECTED"
    schema_version: int = 1
    version: int = 1
    confidence: str = "Review recommended"
    confirmed: bool = False
    fingerprint: str = ""
    warnings: tuple[str, ...] = ()
    matched_profile_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def mapping(self):
        return dict(self.column_mapping)

    def as_dict(self):
        from dataclasses import asdict
        structure = asdict(self.structure)
        structure["comment_prefixes"] = list(self.structure.comment_prefixes)
        return {"schema_version": self.schema_version, "id": self.id, "name": self.name,
                "version": self.version, "source": self.source, "input_type": self.input_type,
                "parser_kind": "WHITESPACE" if self.structure.delimiter == "whitespace" else "DELIMITED",
                "structure": structure, "column_mapping": self.mapping,
                "detection_metadata": {"confidence": self.confidence, "confirmed": self.confirmed,
                                       "fingerprint": self.fingerprint, "warnings": list(self.warnings),
                                       "matched_profile_id": self.matched_profile_id},
                "output_policy": {"preserve_source_structure": True},
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, value, check=True):
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("Unsupported format profile schema; expected schema_version=1")
        s = value.get("structure", {})
        if not isinstance(s, dict): raise ValueError("Invalid profile structure")
        mapping = value.get("column_mapping", {})
        if not isinstance(mapping, dict): raise ValueError("Invalid profile column mapping")
        meta = value.get("detection_metadata", {})
        if not isinstance(meta, dict): raise ValueError("Invalid profile detection metadata")
        warnings = meta.get("warnings", [])
        if not isinstance(warnings, (list, tuple)) or any(not isinstance(item, str) for item in warnings):
            raise ValueError("Invalid profile warnings")
        try:
            structure = Structure(**{**s, "comment_prefixes": tuple(s.get("comment_prefixes", ("#", "%", "//")))})
            profile = cls(str(value["id"]), str(value["name"]), value["input_type"], structure,
                          tuple(sorted(mapping.items())), value.get("source", "DETECTED"),
                          version=value.get("version", 1), confidence=meta.get("confidence", "Review recommended"),
                          confirmed=meta.get("confirmed", False) is True, fingerprint=meta.get("fingerprint", ""),
                          warnings=tuple(warnings), matched_profile_id=meta.get("matched_profile_id"),
                          created_at=value.get("created_at", ""), updated_at=value.get("updated_at", ""))
        except (AttributeError, TypeError, KeyError, ValueError) as exc:
            raise ValueError("Invalid format profile JSON") from exc
        if check: profile.check_syntax()
        return profile

    def check_syntax(self):
        s = self.structure
        if not self.id or not self.name or any(c in self.id + self.name for c in '\r\n'): raise ValueError("Profile id and name must be single-line text")
        if type(self.version) is not int or self.version < 1: raise ValueError("Invalid profile version")
        if self.input_type not in ROLES: raise ValueError("Invalid input type")
        # CUSTOM is a transient renderer working-copy marker.  ProfileStore
        # rewrites it to USER when the operator saves a profile.
        if self.source not in ("DETECTED", "BUILTIN", "USER", "CUSTOM"):
            raise ValueError("Invalid profile source")
        if self.confidence not in ("High confidence", "Review recommended", "Unresolved"):
            raise ValueError("Invalid profile confidence")
        if type(self.confirmed) is not bool: raise ValueError("Invalid profile confirmation state")
        if s.header_mode not in ("PRESENT", "ABSENT"): raise ValueError("Header must be resolved before use")
        if s.delimiter not in DELIMITERS and (not isinstance(s.delimiter, str) or len(s.delimiter) != 1 or s.delimiter in '\r\n"'):
            raise ValueError("Choose a supported or custom single-character delimiter")
        if not isinstance(s.quote_char, str) or len(s.quote_char) != 1 or s.quote_char in '\r\n': raise ValueError("Invalid quote character")
        if s.separator == s.quote_char: raise ValueError("Delimiter and quote character must differ")
        if s.encoding not in ("AUTO", "utf-8", "utf-8-sig", "cp1252", "latin-1"): raise ValueError("Unsupported encoding")
        if any(type(n) is not int or n < 0 for n in (s.skip_rows, s.header_row)): raise ValueError("Row offsets must be non-negative integers")
        if any(not isinstance(p, str) or not p or '\n' in p or '\r' in p for p in s.comment_prefixes): raise ValueError("Invalid comment prefixes")
        if s.delimiter == "semicolon" and ";" in s.comment_prefixes: raise ValueError("Semicolon delimiter cannot also be a comment prefix")
        if set(self.mapping) != set(ROLES[self.input_type]): raise ValueError("Map every required canonical role exactly once")
        indices = list(self.mapping.values())
        if any(type(i) is not int or i < 0 for i in indices): raise ValueError("Column indices must be non-negative integers")
        if len(set(indices)) != len(indices): raise ValueError("One column cannot have two canonical roles")

    @property
    def profile_hash(self):
        value = self.as_dict()
        # Detection confidence, timestamps and operator confirmation do not change parsing.
        for key in ("detection_metadata", "created_at", "updated_at"): value.pop(key)
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def builtin_profiles():
    return [FormatProfile("builtin-eiva-standard", "EIVA Standard CSV", "EIVA", Structure(), tuple(zip(ROLES["EIVA"], (0, 1, 2))), "BUILTIN"),
            FormatProfile("builtin-recorder-standard", "Recorder Standard Header", "RECORDER", Structure("whitespace"), tuple(zip(ROLES["RECORDER"], (0, 1, 2))), "BUILTIN"),
            FormatProfile("builtin-pronav-3col", "Pronav 3-column", "RECORDER", Structure("comma", "ABSENT"), tuple(zip(ROLES["RECORDER"], (0, 1, 2))), "BUILTIN")]


class ProfileStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("APPDATA", Path.home())) / "ShotLogFixer" / "profiles" / "format-profiles.json"

    def load(self):
        if not self.path.exists(): return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Unable to read stored format profiles") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported stored profile schema")
        stored = data.get("profiles")
        if not isinstance(stored, list): raise ValueError("Invalid stored profile list")
        try:
            profiles = [FormatProfile.from_dict(p) for p in stored]
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid stored format profile") from exc
        if any(p.source != "USER" or p.id.startswith("builtin-") for p in profiles): raise ValueError("Invalid user profile store")
        if len({p.id for p in profiles}) != len(profiles): raise ValueError("Duplicate stored profile ids")
        return profiles

    def _write(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": 1, "profiles": [p.as_dict() for p in profiles]}, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def save(self, profile, name, profile_id=None):
        profile.check_syntax()
        if not isinstance(name, str) or not name.strip() or any(c in name for c in '\r\n'): raise ValueError("Enter a single-line profile name")
        profiles = self.load()
        previous = next((p for p in profiles if p.id == profile_id), None)
        if profile_id and not previous: raise ValueError("Only user profiles can be edited")
        now = datetime.now(timezone.utc).isoformat()
        saved = replace(profile, id=profile_id or f"user-{uuid.uuid4()}", name=name.strip(), source="USER",
                        version=previous.version + 1 if previous else 1,
                        created_at=previous.created_at if previous else now, updated_at=now)
        self._write([p for p in profiles if p.id != saved.id] + [saved])
        return saved

    def delete(self, profile_id):
        profiles = self.load()
        if not any(p.id == profile_id for p in profiles): raise ValueError("Only user profiles can be deleted")
        self._write([p for p in profiles if p.id != profile_id])
