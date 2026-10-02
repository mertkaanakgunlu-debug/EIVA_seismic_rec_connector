"""Correction: build a corrected COPY of the target file from the alignment.

Correction answers one question: *which target row belongs to each authoritative reference record, and which FFID
does that row receive?*  The corrected copy is built from the target file only (never from reference rows):

* every associated target row is kept, byte for byte, except that its mapped FFID field becomes the reference FFID;
* every target row without a reference record is removed;
* header, preamble, comments, blank lines, delimiters, quoting, line endings and encoding are preserved.

A valid reference record that no target row can hold (``alignment.unplaced_reference_rows``) has nothing to renumber, so
it is absent from the copy; it stays visible as a ``BLOCKED`` result row and a severe QC finding.  It does not block the
copy: that would withhold every correct association because of one shot the target log lacks.

QC observations (large distances, coordinate jumps, FFID gaps ...) never enter this module.  The only things that block
a corrected copy are structural impossibilities, listed in ``build_correction_plan``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Optional, Sequence

from .alignment import AlignmentResult
from .format_profiles import FormatProfile
from .models import INVALID, SourceRecord
from .table_parser import replace_fields

KEEP_AND_RENUMBER = "KEEP_AND_RENUMBER"
DROP_TARGET_ONLY = "DROP_TARGET_ONLY"
DROP_INVALID_TARGET = "DROP_INVALID_TARGET"


class CorrectionNotValidatedError(RuntimeError):
    pass


@dataclass(frozen=True)
class Blocker:
    """A structural impossibility.  Unlike a QC warning, it prevents a corrected copy from being written."""
    code: str
    message: str


@dataclass
class CorrectionAction:
    action: str
    target_row: int
    target_line_number: int
    original_ffid: str
    reference_row: Optional[int] = None
    corrected_ffid: Optional[str] = None
    distance_m: Optional[float] = None
    corrected_raw: Optional[str] = None      # the exact text written for a kept row
    reason: str = ""


@dataclass
class CorrectionPlan:
    actions: list[CorrectionAction] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    reference_valid: int = 0
    assigned: int = 0
    reference_without_target: int = 0         # valid reference records no target row could hold (absent from the copy)
    target_only_removed: int = 0
    invalid_target_removed: int = 0

    @property
    def safe_to_build(self) -> bool:
        return not self.blockers

    @property
    def corrected_rows(self) -> int:
        return self.assigned

    @property
    def expected_rows(self) -> int:
        """The valid reference records: the corrected copy has one row for each that received a target row."""
        return self.reference_valid


def sha256_file(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def build_correction_plan(reference: Sequence[SourceRecord], target: Sequence[SourceRecord],
                          alignment: AlignmentResult, target_profile: FormatProfile) -> CorrectionPlan:
    """Decide the fate of every target row and list the structural blockers (never QC warnings)."""
    plan = CorrectionPlan(reference_valid=alignment.reference_valid,
                          reference_without_target=len(alignment.unplaced_reference_rows))
    invalid_reference = [r for r in reference if r.classification == INVALID]
    if invalid_reference:
        first = invalid_reference[0]
        plan.blockers.append(Blocker(
            "REFERENCE_ROWS_INVALID",
            f"{len(invalid_reference)} recorder row(s) cannot be interpreted (first: line {first.source_line_number}, {first.invalid_reason}). "
            "They can be neither assigned nor safely discarded; correct the source or the format profile."))
    if not alignment.reference_valid:
        plan.blockers.append(Blocker("NO_REFERENCE_RECORDS", "The recorder log contains no valid records to assign."))
    if not target:
        plan.blockers.append(Blocker("NO_TARGET_ROWS", "The target file contains no data rows."))
    elif len(target) < alignment.reference_valid:
        plan.blockers.append(Blocker(
            "INSUFFICIENT_TARGET_ROWS",
            f"The target has {len(target)} rows but the recorder has {alignment.reference_valid} valid records; "
            "a one-to-one assignment is impossible."))

    ffid_index = target_profile.mapping["FFID"]
    unwritable = []
    for t in target:
        pair = alignment.by_target.get(t.row_index)
        if pair is None:
            invalid = t.classification == INVALID
            plan.actions.append(CorrectionAction(DROP_INVALID_TARGET if invalid else DROP_TARGET_ONLY, t.row_index, t.source_line_number,
                                                 t.original_ffid, reason="No recorder record; removed from the corrected copy."))
            plan.invalid_target_removed += invalid
            plan.target_only_removed += not invalid
            continue
        ffid = reference[pair.reference_row].original_ffid
        corrected = None
        if t.ffid_cell_present:
            try:
                corrected = replace_fields(t.raw, {ffid_index: ffid}, target_profile.structure)
            except (IndexError, ValueError):
                corrected = None
        if corrected is None:
            unwritable.append(t)
        plan.actions.append(CorrectionAction(KEEP_AND_RENUMBER, t.row_index, t.source_line_number, t.original_ffid, pair.reference_row,
                                             ffid, pair.distance_m, corrected, "Associated with an authoritative recorder record."))
        plan.assigned += 1
    if unwritable:
        plan.blockers.append(Blocker(
            "TARGET_FFID_FIELD_MISSING",
            f"{len(unwritable)} associated target row(s) have no FFID field to replace (first: line {unwritable[0].source_line_number})."))
    return plan


def build_corrected_text(target_text: str, target: Sequence[SourceRecord], plan: CorrectionPlan) -> str:
    """Assemble the corrected copy: kept rows renumbered, removed rows dropped, everything else verbatim."""
    lines = target_text.splitlines(keepends=True)
    by_first_line = {t.source_line_number: t for t in target}
    action_by_row = {a.target_row: a for a in plan.actions}
    out, i = [], 1
    while i <= len(lines):
        record = by_first_line.get(i)
        if record is None:
            out.append(lines[i - 1])
            i += 1
            continue
        action = action_by_row[record.row_index]
        if action.corrected_raw is not None:
            out.append(action.corrected_raw)
        i = record.source_end_line_number + 1
    return "".join(out)


# ------------------------------------------------------------------------------------------------------
# Guarded local writes
# ------------------------------------------------------------------------------------------------------

def _guard_output(path: Path, sources: Sequence[Path], overwrite: bool):
    resolved = path.resolve()
    if any(resolved == source.resolve() or (path.exists() and os.path.samefile(path, source)) for source in sources):
        raise ValueError("The corrected copy must not overwrite either source file")
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Output is not a file: {path}")


def _write_temp(path: Path, content: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return temp
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def write_new_file(path: Path, content: bytes, sources: Sequence[Path], overwrite: bool, verify_sources) -> Path:
    """Stage the content, re-verify the sources, then install it atomically; a failure leaves nothing behind."""
    _guard_output(path, sources, overwrite)
    temp = _write_temp(path, content)
    backup = None
    installed = False
    try:
        verify_sources()
        _guard_output(path, sources, overwrite)
        if overwrite and path.exists():
            backup = _write_temp(path, path.read_bytes())
        if overwrite:
            os.replace(temp, path)
        else:
            try:
                os.link(temp, path)          # an exclusive link prevents an unconfirmed overwrite race
                temp.unlink()
            except FileExistsError:
                raise
            except OSError:
                # Some file systems (FAT/exFAT, network shares) have no hard links; fall back to a plain rename.
                if path.exists():
                    raise FileExistsError(f"Output already exists: {path}")
                os.replace(temp, path)
        installed = True
        if path.read_bytes() != content:
            raise OSError(f"Corrected output verification failed: {path}")
        verify_sources()
    except BaseException as exc:
        problems = []
        if installed:
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                problems.append(str(error))
        if backup is not None:
            try:
                os.replace(backup, path)
                backup = None
            except OSError as error:
                problems.append(f"Restore {path} from {backup}: {error}")
        if problems:
            raise OSError(f"Corrected output operation failed: {exc}. Rollback needs attention: {'; '.join(problems)}") from exc
        raise
    finally:
        temp.unlink(missing_ok=True)
        if backup is not None and path.exists():
            backup.unlink(missing_ok=True)
    return path
