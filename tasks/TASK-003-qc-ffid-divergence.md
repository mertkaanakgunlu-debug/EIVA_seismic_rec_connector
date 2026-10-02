# TASK-003 — QC finding for recorder/EIVA FFID divergence

## Objective
When the relationship between recorder FFIDs and the EIVA original FFIDs of their assigned rows changes along the line
(for example recorder 104 ↔ EIVA 104, then recorder 105 ↔ EIVA 207), QC must report it as an explicit finding so the
operator sees the FFID/sequence divergence. Today it only shows indirectly, as a recorder position jump and a
target-only block.

## Scope
- In `shotlogfixer/qc.py`, add one association-scope finding, code `ASSOCIATION_FFID_OFFSET_CHANGE`, severity
  `WARNING`, emitted once for each pair of consecutive **assigned** reference records where both FFIDs parse as integers
  and `(target_ffid - reference_ffid)` differs from the previous assigned pair. Message names both FFID pairs and the
  old and new offset; `metrics` carries `previous_offset` and `offset`. Attach it to the later reference record.
- Skip pairs where either FFID is not an integer (target FFIDs are free text by design).
- Add the code's human label to `shotlogfixer/presentation.py` and `desktop/src/lib/presentation.ts` so the table and
  the QC TXT show a readable name.
- Update the golden expectations where this new code now appears (scenario 3 at minimum).

## Non-goals
- The finding must not change any association, the corrected copy, or correction blockers (QC never feeds back).
- No change to `alignment.py`, `correction.py` or `validation.py`.
- No new UI counter or navigation group.
- No reporting of a constant offset (an offset that never changes is not a finding).

## Relevant components/files
- `shotlogfixer/qc.py`: `_association_findings`, `_ffid_number`, `Finding`, `run_qc`.
- `shotlogfixer/presentation.py`: `qc_label`.
- `desktop/src/lib/presentation.ts`: `QC_LABELS`.
- `tests/test_qc.py`, `tests/golden/` (from TASK-001).

## Acceptance criteria
- Golden scenario 3 (recorder 104→105 while EIVA 104→207) reports exactly one `ASSOCIATION_FFID_OFFSET_CHANGE`, on
  recorder FFID 105, and its assignments and corrected copy are unchanged.
- A line with a constant non-zero offset (e.g. recorder 1.., EIVA 11..) reports no such finding.
- A target with non-integer FFIDs reports no such finding and no error.
- `test_qc.py::test_running_qc_does_not_touch_the_alignment` and `test_correction.py::test_qc_cannot_change_the_correction`
  still pass.
- QC TXT export lists the new code with its label.

## Required tests
- During implementation: `python -m pytest tests/test_qc.py tests/test_golden.py`
- Task completion: `python -m pytest`, and from `desktop/`: `npm run typecheck && npm run test`

## Dependencies
TASK-001, TASK-002 (both edit `qc.py` and the golden expectations).
