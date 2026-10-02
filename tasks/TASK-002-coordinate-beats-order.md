# TASK-002 — Do not let order override a clearly better coordinate match

## Objective
Today the alignment must place every valid recorder record on a target row, in order. When one recorder shot has no
EIVA row (and an extra EIVA row appears later), order forces a whole run of recorder records onto the row one place
away from their physical shot, each about one shot interval off while a near-zero-distance row sits next door. QC
flags it (`ASSOCIATION_RUN_DISPLACED`) but the corrected copy carries the wrong FFIDs on that run. PROJECT_GOAL.md says
order must not override a clearly better coordinate match. After this task, the alignment leaves that recorder record
without a target row and keeps every other record on its physically matching row.

## Scope
- `shotlogfixer/alignment.py`: let the ordered one-to-one alignment leave a valid reference record unassigned, at a
  fixed cost of `cap` (the same saturation cost already used for an unusable position, `5 × shot interval`). Result:
  a single recorder-only record is preferred over a displaced run longer than about five records; short or flat-evidence
  cases keep today's behaviour. Report such records in a new `AlignmentResult` list (e.g.
  `recorder_only_reference_rows`), distinct from `unplaced_reference_rows` (target too short).
- `shotlogfixer/qc.py`: one finding per such record, code `RECORDER_ONLY`, severity `WARNING`, naming the recorder FFID
  and its neighbours' target rows.
- `shotlogfixer/correction.py` / `validation.py`: a recorder-only record is not a correction blocker; the corrected copy
  simply has no row for it (there is no EIVA row to carry the FFID). Adjust the structural validation's expected row
  count to "assigned records", not "valid recorder records".
- `shotlogfixer/analysis.py` / `engine_cli.py`: surface the record with association `RECORDER_ONLY`; add its label in
  `shotlogfixer/presentation.py` and `desktop/src/lib/presentation.ts` / `types.ts`.
- `docs/recorder-authority-model.md`: update the invariant "every valid reference record is assigned whenever n ≥ m"
  and the "Known limitations" order paragraph.
- Update the existing tests that pin the old behaviour (below) and the golden expectation for the recorder-only scenario.

## Non-goals
- No change to how distance is computed, the `cap` value, the corridor search, or the ambiguity logic.
- No estimation of systematic along-track offsets (the "recorder leads by one shot" case with equal row counts stays as
  is; there is no spare row, so order is not overriding anything there).
- No new UI counter or navigation group.

## Relevant components/files
- `shotlogfixer/alignment.py`: `embed_ordered`, `_cost_function`, `align_records`, `AlignmentResult`.
- `shotlogfixer/qc.py`: `_association_findings`, `run_qc`.
- `shotlogfixer/correction.py`: `build_correction_plan`; `shotlogfixer/validation.py`.
- `tests/test_correction.py::test_recorder_only_shot_displaces_a_run_until_an_extra_target_row_absorbs_it` (the
  scenario this task fixes), `tests/test_alignment.py` (exhaustive-oracle tests must cover the new skip option).

## Acceptance criteria
- In the scenario of `test_recorder_only_shot_displaces_a_run_...` (shot 40 missing from EIVA, shot 79 logged twice):
  recorder FFID 340 is `RECORDER_ONLY` with a `RECORDER_ONLY` QC finding; every other recorder FFID is assigned to the
  target row at its own position (distance ≈ 0); no `ASSOCIATION_RUN_DISPLACED`; the corrected copy is written.
- A single isolated recorder coordinate spike is still assigned (not made recorder-only): the existing case-4 tests in
  `test_alignment.py` and `test_correction.py` pass unchanged.
- The 104 → 105 / ~207 golden scenario is unchanged.
- The exhaustive-oracle test in `test_alignment.py` is extended to the new cost model and passes.
- QC still cannot change the alignment (`test_running_qc_does_not_touch_the_alignment`,
  `test_qc_cannot_change_the_correction` pass).
- Input files are never modified.

## Required tests
- During implementation: `python -m pytest tests/test_alignment.py tests/test_correction.py`
- Task completion: `python -m pytest`, and from `desktop/`: `npm run typecheck && npm run test`

## Dependencies
TASK-001 (golden dataset must exist, including the recorder-only scenario, so the change is visible against it).
