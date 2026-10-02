"""One reconciliation run: parse both inputs, align reference -> target, run QC, plan and validate the correction.

The three results are deliberately independent:

* ``alignment``  which target row belongs to each authoritative reference record;
* ``findings``   QC observations for a human to inspect (never feed back into the alignment or the plan);
* ``plan``       the correction decision, blocked only by structural impossibilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Optional

from .alignment import Association, AlignmentResult, align_records
from .analysis_parameters import AnalysisParameters
from .canonical_mapping import map_records
from .correction import (Blocker, CorrectionNotValidatedError, CorrectionPlan, build_corrected_text,
                         build_correction_plan, sha256_file, write_new_file)
from .models import (ASSIGNED, BLOCKED, INVALID, INVALID_ROW, NO_SHOT, NO_SHOT_ROW, SEVERITY_ORDER, TARGET_ONLY,
                     SourceRecord, VALID)
from .profile_validation import require_valid
from .qc import Finding, association_confidence, run_qc, worst_severity
from .source_reader import decode_source
from .table_parser import parse_table
from .validation import ValidationResult, validate_corrected_copy


@dataclass
class ResultRow:
    """One line of the acquisition-ordered result: a pair, a target-only row, or a reference record without a target row."""
    id: str
    association: str
    position: int
    reference: Optional[SourceRecord] = None
    target: Optional[SourceRecord] = None
    pair: Optional[Association] = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def qc_severity(self) -> Optional[str]:
        return worst_severity(self.findings)

    @property
    def corrected_ffid(self) -> Optional[str]:
        return self.reference.original_ffid if self.association == ASSIGNED and self.reference else None


@dataclass
class Analysis:
    parameters: AnalysisParameters
    reference_profile: object
    target_profile: object
    reference_path: Path
    target_path: Path
    reference_text: str
    target_text: str
    reference_encoding: str
    target_encoding: str
    input_hashes: dict
    reference: list[SourceRecord]
    target: list[SourceRecord]
    alignment: AlignmentResult
    findings: list[Finding]
    plan: CorrectionPlan
    validation: ValidationResult
    corrected_text: Optional[str] = None
    rows: list[ResultRow] = field(default_factory=list)

    def verify_sources(self):
        for key, path in (("reference", self.reference_path), ("target", self.target_path)):
            if sha256_file(path) != self.input_hashes.get(key):
                raise CorrectionNotValidatedError("An input file changed since analysis; analyse again")

    def save_corrected(self, output_path, overwrite: bool = False) -> Path:
        """Write the corrected COPY of the target file.  Neither input file is ever modified."""
        if not self.plan.safe_to_build or self.corrected_text is None or not self.validation.passed:
            raise CorrectionNotValidatedError("Correction is blocked: " + "; ".join(b.message for b in self.plan.blockers))
        self.verify_sources()
        # Independent re-validation at the write boundary.
        again = validate_corrected_copy(self.target_text, self.corrected_text, self.reference, self.target,
                                        self.alignment, self.plan, self.target_profile)
        if not again.passed:
            raise CorrectionNotValidatedError("; ".join(again.errors))
        return write_new_file(Path(output_path), self.corrected_text.encode(self.target_encoding),
                              [self.target_path, self.reference_path], overwrite, self.verify_sources)


class InputError(ValueError):
    """An input file could not be read or interpreted; ``role`` names which one."""

    def __init__(self, role: str, kind: str, message: str):
        super().__init__(message)
        self.role, self.kind = role, kind          # kind: PERMISSION | INVALID


def _load(path: Path, profile, role: str):
    try:
        raw = path.read_bytes()
        text, encoding = decode_source(raw, profile.structure.encoding)
        table = parse_table(text, profile)
        require_valid(profile, table)
        return hashlib.sha256(raw).hexdigest(), text, encoding, map_records(table, profile)
    except PermissionError as exc:
        raise InputError(role, "PERMISSION", str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise InputError(role, "INVALID", str(exc)) from exc


def run_analysis(reference_path, target_path, parameters: AnalysisParameters, reference_profile, target_profile) -> Analysis:
    reference_path, target_path = Path(reference_path).resolve(), Path(target_path).resolve()
    ref_hash, ref_text, ref_encoding, reference = _load(reference_path, reference_profile, "REFERENCE")
    tgt_hash, tgt_text, tgt_encoding, target = _load(target_path, target_profile, "TARGET")
    alignment = align_records(reference, target, parameters)
    findings = run_qc(reference, target, alignment, parameters)
    plan = build_correction_plan(reference, target, alignment, target_profile)
    corrected, validation = None, ValidationResult(expected_rows=plan.expected_rows)
    if plan.safe_to_build:
        corrected = build_corrected_text(tgt_text, target, plan)
        validation = validate_corrected_copy(tgt_text, corrected, reference, target, alignment, plan, target_profile)
        if not validation.passed:
            plan.blockers.append(Blocker("CORRECTED_COPY_FAILED_VALIDATION", "; ".join(validation.errors)))
    else:
        validation.errors = [b.message for b in plan.blockers]
    analysis = Analysis(parameters, reference_profile, target_profile, reference_path, target_path, ref_text, tgt_text,
                        ref_encoding, tgt_encoding, {"reference": ref_hash, "target": tgt_hash}, reference, target,
                        alignment, findings, plan, validation, corrected)
    analysis.verify_sources()
    analysis.rows = build_rows(analysis)
    return analysis


def build_rows(analysis: Analysis) -> list[ResultRow]:
    """Interleave pairs, target-only rows and unplaced reference records in acquisition order."""
    alignment, reference, target = analysis.alignment, analysis.reference, analysis.target
    trailing: dict[int, list[SourceRecord]] = {}
    previous = -1
    for r in reference:
        if r.row_index in alignment.by_reference:
            previous = r.row_index
        else:
            trailing.setdefault(previous, []).append(r)
    rows: list[ResultRow] = []
    position = 1

    def reference_only(records):
        for r in records:
            kind = INVALID_ROW if r.classification == INVALID else NO_SHOT_ROW if r.classification == NO_SHOT else BLOCKED
            rows.append(ResultRow(f"row-{len(rows) + 1}", kind, position, reference=r))

    reference_only(trailing.get(-1, []))
    for t in target:
        position = t.row_index + 1
        pair = alignment.by_target.get(t.row_index)
        if pair is None:
            kind = INVALID_ROW if t.classification == INVALID else TARGET_ONLY
            rows.append(ResultRow(f"row-{len(rows) + 1}", kind, position, target=t))
            continue
        rows.append(ResultRow(f"row-{len(rows) + 1}", ASSIGNED, position, reference[pair.reference_row], t, pair))
        reference_only(trailing.get(pair.reference_row, []))
    by_reference = {row.reference.row_index: row for row in rows if row.reference}
    by_target = {row.target.row_index: row for row in rows if row.target}
    for finding in analysis.findings:
        row = by_reference.get(finding.reference_row) if finding.reference_row is not None else None
        if row is None and finding.target_row is not None:
            row = by_target.get(finding.target_row)
        if row is not None:
            row.findings.append(finding)
    for row in rows:
        row.findings.sort(key=lambda f: -SEVERITY_ORDER[f.severity])
    return rows


def row_confidence(row: ResultRow, parameters) -> Optional[str]:
    return association_confidence(row.pair, parameters) if row.pair else None
