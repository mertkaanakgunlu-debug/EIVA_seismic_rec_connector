"""Independent structural validation of a corrected copy.

These checks establish that the corrected copy is a faithful, internally consistent product of the alignment: the FFIDs
come from the reference, nothing but the FFID field changed, the file structure survived, and the assignment is
one-to-one and order preserving.  They contain no distance or tolerance test: spatial observations are QC, and QC never
decides whether a corrected copy may be written.
"""

from dataclasses import dataclass, field
from typing import Any, Sequence

from .alignment import AlignmentResult
from .canonical_mapping import parse_canonical
from .correction import KEEP_AND_RENUMBER, CorrectionPlan
from .models import SourceRecord, VALID
from .table_parser import parse_table


@dataclass
class ValidationResult:
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    corrected_rows: int = 0
    expected_rows: int = 0
    ffid_changed: int = 0
    ffid_unchanged: int = 0
    checks: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "errors": self.errors, "corrected_rows": self.corrected_rows,
                "expected_rows": self.expected_rows, "ffid_changed": self.ffid_changed,
                "ffid_unchanged": self.ffid_unchanged, "checks": self.checks}


def validate_corrected_copy(original_text: str, corrected_text: str, reference: Sequence[SourceRecord],
                            target: Sequence[SourceRecord], alignment: AlignmentResult, plan: CorrectionPlan,
                            profile) -> ValidationResult:
    result = ValidationResult(expected_rows=plan.expected_rows)
    kept = [a for a in plan.actions if a.action == KEEP_AND_RENUMBER]
    reference_rows = [a.reference_row for a in kept]
    target_rows = [a.target_row for a in kept]
    checks = result.checks
    checks["one_to_one"] = len(set(reference_rows)) == len(reference_rows) and len(set(target_rows)) == len(target_rows)
    checks["order_preserved"] = (all(a < b for a, b in zip(reference_rows, reference_rows[1:]))
                                 and all(a < b for a, b in zip(target_rows, target_rows[1:])))
    checks["only_valid_reference_records"] = all(reference[r].classification == VALID for r in reference_rows)
    # No valid reference record may vanish: each is either in the copy or reported as having no target row.
    checks["every_valid_reference_record_accounted_for"] = (len(kept) + len(alignment.unplaced_reference_rows) == plan.reference_valid
                                                            and set(reference_rows).isdisjoint(alignment.unplaced_reference_rows))
    try:
        output = parse_canonical(corrected_text, profile)
        original_table, corrected_table = parse_table(original_text, profile), parse_table(corrected_text, profile)
    except ValueError as exc:
        result.errors.append(f"The corrected copy cannot be parsed with the target format: {exc}")
        result.checks.update({"row_count": False, "ffids_from_reference": False, "unrelated_fields_unchanged": False,
                              "structure_preserved": False})
        return result
    result.corrected_rows = len(output)
    checks["row_count"] = len(output) == len(kept)
    checks["ffids_from_reference"] = [o.original_ffid for o in output] == [a.corrected_ffid for a in kept]
    ffid_index = profile.mapping["FFID"]
    unrelated = len(output) == len(kept)
    if unrelated:
        for action, produced in zip(kept, output):
            source = target[action.target_row]
            if len(source.cells) != len(produced.cells) or any(
                    a != b for i, (a, b) in enumerate(zip(source.cells, produced.cells)) if i != ffid_index):
                unrelated = False
                break
    checks["unrelated_fields_unchanged"] = unrelated
    checks["structure_preserved"] = (original_table.header == corrected_table.header and
                                     [raw for _, raw in original_table.skipped_lines] == [raw for _, raw in corrected_table.skipped_lines])
    result.ffid_changed = sum(a.original_ffid != a.corrected_ffid for a in kept)
    result.ffid_unchanged = len(kept) - result.ffid_changed
    messages = {
        "one_to_one": "A reference record or target row is used more than once",
        "order_preserved": "The assignment does not preserve acquisition order",
        "only_valid_reference_records": "A reference record that is not valid was used as an FFID source",
        "row_count": "The corrected copy does not contain exactly the assigned rows",
        "every_valid_reference_record_accounted_for": "A valid reference record is neither in the corrected copy nor reported as unplaced",
        "ffids_from_reference": "The corrected FFIDs are not the reference FFIDs, in reference order",
        "unrelated_fields_unchanged": "A field other than the FFID differs from the source row",
        "structure_preserved": "The header or the non-record lines of the target file changed",
    }
    for key, message in messages.items():
        if not checks.get(key, True):
            result.errors.append(message)
    result.passed = not result.errors
    return result
