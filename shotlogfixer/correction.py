"""Deterministic correction, token-preserving candidates and guarded local writes."""

from __future__ import annotations

import csv
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
from dataclasses import dataclass, field

from .matcher import match_records
from .analysis_parameters import AnalysisParameters
from .gap_analysis import analyse_recorder_gaps, validate_gap_events
from .models import CorrectionAction, CorrectionPlan, EivaRecord, MatchResult, RecorderRecord, ValidationResult, RecorderGapEvent
from .parsers import classify_recorder_row, decode_source, parse_eiva_text, parse_recorder_text
from .validation import validate_candidates, validate_serialized


class CorrectionNotValidatedError(RuntimeError):
    pass


@dataclass
class CorrectionBundle:
    eiva_records: list[EivaRecord]
    recorder_records: list[RecorderRecord]
    results: list[MatchResult]
    plan: CorrectionPlan
    eiva_text: str = ""
    recorder_text: str = ""
    validation: ValidationResult | None = None
    input_hashes: dict[str, str] = field(default_factory=dict)
    eiva_path: Path | None = None
    recorder_path: Path | None = None
    eiva_encoding: str = "utf-8"
    recorder_encoding: str = "utf-8"
    parameters: AnalysisParameters = field(default_factory=lambda: AnalysisParameters(2.0))
    recorder_gaps: list[RecorderGapEvent] = field(default_factory=list)
    eiva_profile: object | None = None
    recorder_profile: object | None = None


def sha256_file(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def build_correction_plan(eiva: list[EivaRecord], recorder: list[RecorderRecord], results: list[MatchResult],
                          recorder_gaps: list[RecorderGapEvent] | None = None) -> CorrectionPlan:
    """Resolve only equal, pure NO_SHOT windows between accepted matched anchors."""
    plan = CorrectionPlan(source_eiva_count=len(eiva), source_recorder_count=len(recorder))
    recorder_gaps = recorder_gaps or []
    plan.blocking_reasons.extend(g.diagnostic for g in recorder_gaps if g.blocks_correction)
    elines = {row.source_line_number: i for i, row in enumerate(eiva)}
    rlines = {row.source_line_number: i for i, row in enumerate(recorder)}
    classes = [classify_recorder_row(row) for row in recorder]
    statuses = {row.eiva_record.source_line_number: row.status for row in results if row.eiva_record}
    result_by_ei = {elines[row.eiva_record.source_line_number]: row for row in results if row.eiva_record}
    anchors = [(elines[row.eiva_record.source_line_number], rlines[row.recorder_record.source_line_number], row)
               for row in results if row.status == "MATCHED" and row.eiva_record and row.recorder_record]
    matched = {ei: (ri, row) for ei, ri, row in anchors}
    resolved: dict[int, int] = {}
    plan.invalid_recorder_count = classes.count("INVALID")
    if plan.invalid_recorder_count:
        plan.blocking_reasons.append(f"{plan.invalid_recorder_count} invalid recorder row(s)")
    if any(row.status == "REVIEW" and row.recorder_record for row in results):
        plan.blocking_reasons.append("Unresolved recorder REVIEW: ambiguous or unmatched valid recorder")
    if any(b[0] <= a[0] or b[1] <= a[1] for a, b in zip(anchors, anchors[1:])):
        plan.blocking_reasons.append("Non-monotonic accepted source mappings")
    anchor_pairs = [(-1, -1)] + [(ei, ri) for ei, ri, _ in anchors] + [(len(eiva), len(recorder))]
    for interval, (left, right) in enumerate(zip(anchor_pairs, anchor_pairs[1:])):
        eis = list(range(left[0] + 1, right[0]))
        ris = list(range(left[1] + 1, right[1]))
        ns = [ri for ri in ris if classes[ri] == "NO_SHOT"]
        if not ns:
            continue
        if interval == 0 or interval == len(anchor_pairs) - 2:
            plan.blocking_reasons.append("Boundary NO_SHOT has no two-sided valid anchors")
            continue
        if any(classes[ri] != "NO_SHOT" for ri in ris):
            plan.blocking_reasons.append("Ambiguous NO_SHOT interval contains INVALID or unmatched VALID recorder rows")
            continue
        if len(eis) != len(ns):
            plan.blocking_reasons.append(f"NO_SHOT interval count mismatch ({len(ns)} recorder / {len(eis)} EIVA)")
            continue
        if any(statuses.get(eiva[ei].source_line_number) != "REVIEW" for ei in eis):
            plan.blocking_reasons.append("Ambiguous EIVA candidate region around NO_SHOT")
            continue
        resolved.update(zip(eis, ns))
    for ei, row in enumerate(eiva):
        if ei in matched:
            ri, match = matched[ei]
            plan.actions.append(CorrectionAction("KEEP_AND_RENUMBER", ei, row.original_ffid,
                                                recorder[ri].ffid, ri, recorder[ri].ffid,
                                                "MATCHED", "Accepted coordinate/order anchor", match.distance_m))
        elif ei in resolved:
            ri = resolved[ei]
            plan.actions.append(CorrectionAction("DROP_NO_SHOT", ei, row.original_ffid, None, ri,
                                                recorder[ri].ffid, "NO_SHOT", "Equal bracketed NO_SHOT interval; paired by acquisition order"))
        elif statuses.get(row.source_line_number) == "EIVA_ONLY":
            gap_ids = result_by_ei.get(ei).gap_event_ids if result_by_ei.get(ei) else []
            reason = "No valid recorder coordinate counterpart"
            if gap_ids:
                reason = "Recorder spatial gap; EIVA position has no recorded shot counterpart"
            plan.actions.append(CorrectionAction("DROP_EIVA_ONLY", ei, row.original_ffid,
                                                status="EIVA_ONLY", reason=reason,
                                                gap_event_id=gap_ids[0] if gap_ids else None))
        else:
            plan.blocking_reasons.append(f"Unresolved REVIEW at EIVA line {row.source_line_number}")
    matched_ris = [ri for _, ri, _ in anchors]
    if sorted(matched_ris) != [i for i, kind in enumerate(classes) if kind == "VALID"]:
        plan.blocking_reasons.append("Unmatched valid recorder rows")
    if not matched_ris:
        plan.blocking_reasons.append("No valid paired shots")
    if len(set(matched_ris)) != len(matched_ris) or len(matched) != len(anchors):
        plan.blocking_reasons.append("Duplicate retained source mappings")
    plan.matched_count = len(anchors)
    plan.dropped_eiva_only_count = sum(a.action_type == "DROP_EIVA_ONLY" for a in plan.actions)
    plan.dropped_no_shot_count = len(resolved)
    plan.planned_fixed_eiva_count = plan.matched_count
    plan.planned_fixed_recorder_count = classes.count("VALID")
    plan.blocking_reasons = list(dict.fromkeys(plan.blocking_reasons))
    plan.unresolved_count = len(plan.blocking_reasons)
    plan.safe_to_build = not plan.blocking_reasons
    return plan


def resolve_results(eiva, recorder, raw_results, plan):
    drops = {eiva[a.eiva_source_index].source_line_number: a for a in plan.actions if a.action_type == "DROP_NO_SHOT"}
    resolved_lines = {recorder[a.recorder_source_index].source_line_number for a in drops.values()}
    output = []
    for row in raw_results:
        if row.recorder_record and row.recorder_record.source_line_number in resolved_lines:
            continue
        if row.eiva_record and row.eiva_record.source_line_number in drops:
            action = drops[row.eiva_record.source_line_number]
            resolved_row = MatchResult(row.eiva_record, recorder[action.recorder_source_index], None,
                                      "NO_SHOT", "No shot recorded; remove from fixed pair")
            resolved_row.gap_event_ids = list(row.gap_event_ids)
            output.append(resolved_row)
        elif row.recorder_record and classify_recorder_row(row.recorder_record) == "NO_SHOT":
            output.append(MatchResult(None, row.recorder_record, None, "NO_SHOT",
                                      "No shot recorded; navigation association unresolved"))
        else:
            output.append(row)
    return output


def _csv_tokens(raw: str) -> list[str]:
    """Split on delimiters outside quoted strings, retaining the raw field text."""
    tokens, start, quoted, index = [], 0, False, 0
    while index < len(raw):
        if raw[index] == '"':
            if quoted and index + 1 < len(raw) and raw[index + 1] == '"':
                index += 2
                continue
            quoted = not quoted
        elif raw[index] == ',' and not quoted:
            tokens.append(raw[start:index]); start = index + 1
        index += 1
    tokens.append(raw[start:])
    return tokens


def _replace_token(original: str, value: str) -> str:
    prefix = original[:len(original) - len(original.lstrip())]
    suffix = original[len(original.rstrip()):]
    inner = original.strip()
    escaped = value.replace('"', '""')
    if inner.startswith('"') and inner.endswith('"') or any(ch in value for ch in ',"\r\n'):
        value = f'"{escaped}"'
    return prefix + value + suffix


def build_candidates(eiva_text, recorder_text, eiva, recorder, plan):
    header = next(csv.reader(io.StringIO(eiva_text, newline="")))
    names = [value.strip().lower() for value in header]
    ix = {name: names.index(name) for name in ("ffid", "e(spark)", "n(spark)")}
    eiva_replacements = {}
    recorder_replacements = {}
    for action in plan.actions:
        row = eiva[action.eiva_source_index]
        if action.action_type != "KEEP_AND_RENUMBER":
            eiva_replacements[row.source_line_number] = ""
            if action.action_type == "DROP_NO_SHOT":
                recorder_replacements[recorder[action.recorder_source_index].source_line_number] = ""
            continue
        tokens = _csv_tokens(row.original_line)
        for name, value in (("ffid", action.target_ffid), ("e(spark)", f"{row.easting_spark:.2f}"), ("n(spark)", f"{row.northing_spark:.2f}")):
            tokens[ix[name]] = _replace_token(tokens[ix[name]], value)
        eiva_replacements[row.source_line_number] = ','.join(tokens)
        rec = recorder[action.recorder_source_index]
        spans = list(re.finditer(r"\S+", rec.original_line))
        raw = rec.original_line
        for index, value in ((2, f"{rec.source_y:.2f}"), (1, f"{rec.source_x:.2f}")):
            span = spans[index]; raw = raw[:span.start()] + value + raw[span.end():]
        recorder_replacements[rec.source_line_number] = raw
    def assemble(text, records, replacements):
        lines = text.splitlines(keepends=True)
        starts = {row.source_line_number: row for row in records}
        parts, i = [], 1
        while i <= len(lines):
            if i in starts:
                row = starts[i]
                parts.append(replacements.get(i, ""))
                i = getattr(row, "source_end_line_number", None) or i
            else:
                parts.append(lines[i - 1])
            i += 1
        return ''.join(parts)
    return assemble(eiva_text, eiva, eiva_replacements), assemble(recorder_text, recorder, recorder_replacements)


def build_profile_candidates(eiva_text, recorder_text, eiva, recorder, plan, eiva_profile, recorder_profile):
    """Serialize profile-driven rows while retaining headers, delimiters and unrelated cells."""
    from .table_parser import replace_fields, parse_table
    eiva_table, recorder_table = parse_table(eiva_text, eiva_profile), parse_table(recorder_text, recorder_profile)
    eiva_repl, recorder_repl = {}, {}
    eiva_ix, rec_ix = eiva_profile.mapping, recorder_profile.mapping
    for action in plan.actions:
        if action.eiva_source_index is None: continue
        erow = eiva[action.eiva_source_index]
        if action.action_type == "KEEP_AND_RENUMBER":
            eiva_repl[erow.source_line_number] = replace_fields(erow.original_line, {
                eiva_ix["FFID"]: action.target_ffid,
                eiva_ix["EIVA_EASTING"]: f"{erow.easting_spark:.2f}",
                eiva_ix["EIVA_NORTHING"]: f"{erow.northing_spark:.2f}"}, eiva_profile.structure)
            rec = recorder[action.recorder_source_index]
            recorder_repl[rec.source_line_number] = replace_fields(rec.original_line, {
                rec_ix["FFID"]: rec.ffid, rec_ix["RECORDER_X"]: f"{rec.source_x:.2f}",
                rec_ix["RECORDER_Y"]: f"{rec.source_y:.2f}"}, recorder_profile.structure)
        else:
            eiva_repl[erow.source_line_number] = ""
            if action.action_type == "DROP_NO_SHOT":
                recorder_repl[recorder[action.recorder_source_index].source_line_number] = ""
    def assemble(text, records, replacements):
        lines = text.splitlines(keepends=True)
        by_line = {r.source_line_number: r for r in records}
        out, i = [], 1
        while i <= len(lines):
            row = by_line.get(i)
            if row:
                replacement = replacements.get(i, row.original_line)
                if replacement and not replacement.endswith(("\n", "\r")):
                    replacement += text.splitlines(keepends=True)[i-1][-1:] if text.splitlines(keepends=True)[i-1].endswith(("\n", "\r")) else ""
                out.append(replacement)
                i = getattr(row, "source_end_line_number", None) or i
            else:
                out.append(lines[i-1])
            i += 1
        return ''.join(out)
    return assemble(eiva_text, eiva, eiva_repl), assemble(recorder_text, recorder, recorder_repl)


def prepare_correction(eiva_path: str | Path, recorder_path: str | Path,
                       parameters: AnalysisParameters | None = None, eiva_profile=None, recorder_profile=None) -> CorrectionBundle:
    legacy_direct_call = parameters is None
    parameters = parameters or AnalysisParameters(2.0)
    eiva_path, recorder_path = Path(eiva_path).resolve(), Path(recorder_path).resolve()
    eiva_bytes, recorder_bytes = eiva_path.read_bytes(), recorder_path.read_bytes()
    hashes = {"eiva": hashlib.sha256(eiva_bytes).hexdigest(), "recorder": hashlib.sha256(recorder_bytes).hexdigest()}
    from .source_reader import decode_source as decode
    eiva_text, eencoding = decode(eiva_bytes, eiva_profile.structure.encoding if eiva_profile else "AUTO")
    recorder_text, rencoding = decode(recorder_bytes, recorder_profile.structure.encoding if recorder_profile else "AUTO")
    if (eiva_profile is None) != (recorder_profile is None): raise ValueError("Provide both input format profiles")
    if eiva_profile:
        from .profile_validation import require_valid
        from .table_parser import parse_table
        require_valid(eiva_profile, parse_table(eiva_text,eiva_profile))
        require_valid(recorder_profile, parse_table(recorder_text,recorder_profile))
    eiva, recorder = parse_eiva_text(eiva_text, eiva_profile), parse_recorder_text(recorder_text, recorder_profile)
    raw_results = match_records(eiva, recorder, parameters)
    # Resolve the existing bracketed NO_SHOT semantics before gap attribution;
    # the geometry analyzer must see those explicit events between anchors.
    base_plan = build_correction_plan(eiva, recorder, raw_results, [])
    base_results = resolve_results(eiva, recorder, raw_results, base_plan)
    recorder_gaps = [] if legacy_direct_call else analyse_recorder_gaps(eiva, recorder, base_results, parameters)
    # Carry gap provenance back to the canonical raw result stream used by the
    # Phase 2 correction planner, while retaining resolved NO_SHOT rows for
    # geometry validation.
    raw_by_line = {row.eiva_record.source_line_number: row for row in raw_results if row.eiva_record}
    for row in base_results:
        if row.eiva_record and row.gap_event_ids:
            raw_by_line[row.eiva_record.source_line_number].gap_event_ids = list(row.gap_event_ids)
    plan = build_correction_plan(eiva, recorder, raw_results, recorder_gaps)
    results = resolve_results(eiva, recorder, raw_results, plan)
    bundle = CorrectionBundle(eiva, recorder, results, plan, input_hashes=hashes,
                              eiva_path=eiva_path, recorder_path=recorder_path, eiva_encoding=eencoding, recorder_encoding=rencoding)
    bundle.parameters = parameters
    bundle.recorder_gaps = recorder_gaps
    bundle.eiva_profile, bundle.recorder_profile = eiva_profile, recorder_profile
    if plan.safe_to_build:
        if eiva_profile is None and recorder_profile is None:
            bundle.eiva_text, bundle.recorder_text = build_candidates(eiva_text, recorder_text, eiva, recorder, plan)
        else:
            bundle.eiva_text, bundle.recorder_text = build_profile_candidates(eiva_text, recorder_text, eiva, recorder, plan, eiva_profile, recorder_profile)
        bundle.validation = validate_candidates(eiva, recorder, plan, bundle.eiva_text, bundle.recorder_text, results, parameters, recorder_gaps, eiva_profile, recorder_profile)
    else:
        classes = [classify_recorder_row(row) for row in recorder]
        bundle.validation = ValidationResult(False, len(eiva), len(recorder), classes.count("VALID"),
                                              classes.count("NO_SHOT"), classes.count("INVALID"),
                                              unresolved_review_count=sum(row.status == "REVIEW" for row in results),
                                              shot_interval_m=parameters.shot_interval_m, match_tolerance_m=parameters.match_tolerance_m,
                                              errors=list(plan.blocking_reasons))
    _verify_raw_hashes(bundle)
    return bundle


def _verify_raw_hashes(bundle):
    if not bundle.eiva_path or not bundle.recorder_path or not bundle.input_hashes:
        raise CorrectionNotValidatedError("Missing raw-input provenance")
    for key, path in (("eiva", bundle.eiva_path), ("recorder", bundle.recorder_path)):
        if sha256_file(path) != bundle.input_hashes.get(key):
            raise CorrectionNotValidatedError("Raw input changed since analysis; analyse again")


def _validate_for_write(bundle):
    if not bundle.validation or not bundle.validation.passed:
        raise CorrectionNotValidatedError("Correction validation did not pass")
    _verify_raw_hashes(bundle)
    validation = validate_candidates(bundle.eiva_records, bundle.recorder_records, bundle.plan,
                                     bundle.eiva_text, bundle.recorder_text, bundle.results,
                                     bundle.parameters, bundle.recorder_gaps, bundle.eiva_profile, bundle.recorder_profile)
    if not validation.passed:
        raise CorrectionNotValidatedError('; '.join(validation.errors))


def _guard_output(path, sources, overwrite):
    resolved = path.resolve()
    if any(resolved == source.resolve() or (path.exists() and os.path.samefile(path, source)) for source in sources):
        raise ValueError("Fixed output path must not be either raw input path")
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Output is not a file: {path}")


def _write_temp(path, content):
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        return temp
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _write_outputs(bundle, outputs, overwrite):
    """Stage every file before committing, restoring previous outputs on failure."""
    _validate_for_write(bundle)
    sources = [bundle.eiva_path, bundle.recorder_path]
    for path, _ in outputs: _guard_output(path, sources, overwrite)
    if len({str(path.resolve()).casefold() for path, _ in outputs}) != len(outputs):
        raise ValueError("Fixed pair output paths must be distinct")
    if len(outputs) == 2 and all(path.exists() for path, _ in outputs) and os.path.samefile(outputs[0][0], outputs[1][0]):
        raise ValueError("Fixed pair outputs refer to the same file")
    temps, backups, installed = [], [], []
    try:
        for path, content in outputs:
            temps.append((path, _write_temp(path, content)))
        _verify_raw_hashes(bundle)
        for path, temp in temps:
            _guard_output(path, sources, overwrite)
            if overwrite and path.exists():
                backup = _write_temp(path, path.read_bytes())
                backups.append((path, backup))
            if overwrite:
                os.replace(temp, path)
            else:
                # An exclusive link prevents an unconfirmed overwrite race.
                os.link(temp, path); temp.unlink()
            installed.append(path)
        for path, content in outputs:
            if path.read_bytes() != content:
                raise OSError(f"Fixed output verification failed: {path}")
        _verify_raw_hashes(bundle)
    except BaseException as exc:
        rollback_errors = []
        for path in installed:
            try: path.unlink(missing_ok=True)
            except OSError as error: rollback_errors.append(str(error))
        for path, backup in backups:
            try: os.replace(backup, path)
            except OSError as error: rollback_errors.append(f"Restore {path} from {backup}: {error}")
        if rollback_errors:
            raise OSError(f"Fixed output operation failed: {exc}. Rollback needs attention: {'; '.join(rollback_errors)}") from exc
        raise
    finally:
        for _, temp in temps:
            temp.unlink(missing_ok=True)
        # Preserve backups when rollback failed; otherwise remove them.
        if not any(backup.exists() and not path.exists() for path, backup in backups):
            for _, backup in backups: backup.unlink(missing_ok=True)
    return tuple(path for path, _ in outputs)


def save_fixed_eiva(bundle: CorrectionBundle, output_path: str | Path, sources=None, overwrite: bool = False) -> Path:
    return _write_outputs(bundle, [(Path(output_path), bundle.eiva_text.encode(bundle.eiva_encoding))], overwrite)[0]


def save_fixed_pair(bundle: CorrectionBundle, eiva_output: str | Path, recorder_output: str | Path,
                    sources=None, overwrite: bool = False) -> tuple[Path, Path]:
    return _write_outputs(bundle, [(Path(eiva_output), bundle.eiva_text.encode(bundle.eiva_encoding)),
                                   (Path(recorder_output), bundle.recorder_text.encode(bundle.recorder_encoding))], overwrite)
