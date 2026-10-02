# TASK-001 — Compact golden regression dataset

## Objective
Add a small, committed, deterministic golden dataset that pins the critical matching, QC and correction behaviour of
the current engine, so later tasks have a fast regression net that does not depend on real survey files (the only
real-data test, `tests/test_real_sample.py`, skips when the files are absent).

## Scope
- Add `tests/golden/` with one directory per scenario, each holding a tiny recorder file, a tiny EIVA file (tens of
  rows at most, written by hand or by a checked-in generator) and an `expected.json`.
- Scenarios (one each):
  1. Clean one-to-one alignment.
  2. Extra EIVA rows (target-only) that are removed from the corrected copy.
  3. **FFID divergence**: recorder FFIDs 101–104, recorder stops, recorder resumes at FFID 105 while EIVA has advanced
     to about FFID 207; coordinates identify the same physical shots. Recorder 105 must be assigned to EIVA 207.
  4. A single recorder coordinate spike that is still assigned and flagged by QC.
  5. Invalid and no-shot recorder rows (sentinel `-214748.36480`).
  6. Fewer EIVA rows than valid recorder records (correction blocker).
- `expected.json` per scenario records: the reference-FFID → target-original-FFID assignments, the corrected-copy FFID
  column, the set of QC codes with counts, and the correction blocker codes (empty when none).
- Add `tests/test_golden.py`, parametrised over the scenario directories, that runs the engine through
  `engine_cli.prepare_analysis` (as `tests/helpers.py::analysis_for` does) and compares against `expected.json`.

## Non-goals
- No change to any file under `shotlogfixer/`, `desktop/` or `app.py`.
- No new QC codes or behaviour (FFID-divergence QC is TASK-002).
- No real survey data in the repository.
- No snapshot of full QC message text (codes and counts only, so wording changes do not break it).

## Relevant components/files
- `tests/helpers.py` (`write_reference`, `write_target`, `analysis_for`): file formats and the analysis entry point.
- `shotlogfixer/analysis.py` (`Analysis.rows`, `ResultRow`, `Analysis.plan.blockers`, `Analysis.corrected_text`).
- `shotlogfixer/qc.py` (`Finding.code`).
- `docs/recorder-authority-model.md` for the expected semantics of each scenario.

## Acceptance criteria
- Six scenario directories exist, each under 100 rows per input file, all committed.
- `python -m pytest tests/test_golden.py` passes on the baseline engine without any production code change.
- Scenario 3 asserts explicitly that recorder FFID 105 is assigned to EIVA FFID 207 and that recorder FFIDs 101–104
  are assigned to EIVA FFIDs 101–104.
- Each `expected.json` was checked by hand against the scenario's intent (the PR description states the intended result
  of each scenario in one line), not only generated from current output.
- Input files are byte-identical after the test run.
- Full Python suite still passes and stays under 10 s.

## Required tests
- `python -m pytest tests/test_golden.py`
- `python -m pytest` (task completion)

## Dependencies
None.
