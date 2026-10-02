# ShotLogFixer 0.5.0

Offline utility that reconciles a seismic **recorder log** (the *reference*, authoritative) with an **EIVA/navigation log** (the *target*, the file being corrected). Every valid recorder record is a real shot and its FFID is the authoritative FFID. ShotLogFixer finds, for each valid recorder record, the EIVA row at its position (full-precision X/Y proximity first, then one-to-one and acquisition order, with sequence continuity as tie-breaker and anomaly fallback), writes the recorder FFID onto that EIVA row in a **corrected copy of the EIVA file**, and removes the EIVA rows that no recorder record claims. The recorder file and the original EIVA file are never modified. Quality control is a separate system: it reports what looks unusual for a human to inspect and never changes, hides or blocks the correction. See [docs/recorder-authority-model.md](docs/recorder-authority-model.md) for the model, the algorithm and the invariants.

Run the GUI with `python app.py` (legacy Tkinter fallback) or use the Electron app below. Run tests with `py -m pytest` (a bare `pytest` also works from the repository root). Build the portable Windows release with `npm run package:portable` from `desktop/`. The result is `release/ShotLogFixer-Portable.exe`; it bundles the Python engine and does not require system Python or Node at runtime.

## Matching, correction and QC

* **Association (correction).** Spatial proximity is the primary signal; one-to-one is mandatory; acquisition order is a consistency constraint, not a lag model, so any number of EIVA rows may lie between two consecutive recorder shots (a recorder outage while navigation kept logging) at no cost. The shot interval is *not* a match tolerance: no distance can discard a recorder record. Sequence continuity places records whose own coordinate is anomalous on the free EIVA row between their neighbours. The assignment is the exact optimum of a weighted longest-chain dynamic programme, deterministic and independent of the original EIVA FFIDs.
* **Corrected copy.** Built from the EIVA file only: the mapped FFID field becomes the recorder FFID, unassigned rows are removed, and everything else (header, other fields, coordinates, delimiters, quoting, line endings, encoding) is preserved. When every valid recorder record is assigned the corrected copy has exactly as many data rows as there are valid recorder records. A recorder record that no EIVA row can hold without taking a better-fitting row from another record stays unassigned (`Blocked`, severe QC, priced in the finding) instead of shifting a whole stretch of correct associations by one row; it is absent from the copy and never blocks it.
* **Correction blockers** are structural impossibilities only: recorder rows that cannot be interpreted, no valid recorder record or no target row, fewer EIVA rows than valid recorder records, no FFID field to write, or a corrected copy that fails structural validation.
* **QC findings** are independent and never block output. Recorder QC: invalid or no-shot rows, duplicate FFIDs, FFID gaps and reversals, duplicate coordinates, position jumps and spikes, abnormal spacing, a shot interval that does not match the data. Target QC: unreadable rows, target-only rows and blocks, position jumps, original FFID oddities (diagnostic only). Association QC: elevated/high/severe distance (bands of 0.5, 1 and 5 shot intervals), placement by sequence only, ambiguity, a recorder record with no EIVA row, a nearer row that was not used, and runs of associations displaced by one row.

The result table shows both concepts side by side: **Association** (Assigned, Target-only, Invalid, No shot, Blocked) and **QC** (OK or the most severe observation). A recorder record whose coordinate jumps 200 m is `Assigned` with a `Severe` QC flag, never "unmatched".

## Desktop UI

The GUI provides a horizontally scrollable, acquisition-order timeline with clickable markers coloured by association and QC severity. Counters (Assigned, Target-only, Invalid, Blocked, QC severe, QC warnings, recorder position jumps, recorder FFID jumps) are click-and-cycle navigators. The default table shows the recorder FFID, the original target FFID, the corrected FFID, both coordinates, the association distance, the association and the QC status; a side without a value renders `—`. Optional columns (basis, confidence, diagnostics, line numbers, raw target columns) are enabled with **Columns**. **Save Corrected EIVA** writes the corrected copy; **Export QC** writes the audit TXT. The footer shows the application version.

## Electron/React desktop UI

The UI lives in `desktop/`. Electron owns native file dialogs, Python process execution, path validation, and output writing. The React renderer communicates through a narrow preload bridge; it has no Node integration or unrestricted filesystem access. The Python alignment, QC, correction and report modules remain the authoritative domain engine.

Use Node 18+ and Python 3.11+ for development. From `desktop/`:

```text
npm install
npm run dev
npm run typecheck
npm run test
npm run build
npm run electron:smoke
```

`npm run dev` starts Vite on `http://127.0.0.1:5173` and passes that URL explicitly to Electron. A normal build and the smoke command load `dist/index.html` directly with `file://`; the production renderer has no localhost dependency. Vite uses a relative asset base (`./`) so packaged Electron windows resolve JavaScript and CSS correctly.

The renderer keeps the compact layout and canvas acquisition timeline. The table uses a stable native render path: the former TanStack table/virtualizer combination was isolated as the source of an unbounded Windows Chromium render loop (it reproduced with zero rows and after both theme and analysis updates), so it is no longer on the release path. Development-only diagnostics record Electron renderer lifecycle events, a renderer heartbeat, React render counters, theme phases, analysis IPC/Python/JSON timings, response size and raw-field contribution, and post-commit animation frames. Production builds do not emit those diagnostics. Theme selection remains a controlled menu backed by CSS variables and persisted preference.

To run the diagnostic smoke test, use `npm run electron:smoke`. It clicks the real ThemePicker and Columns controls, waits for two animation frames after each theme change, and verifies heartbeat progress. An analysis smoke pass can be added by setting `SHOTLOGFIXER_SMOKE_EIVA` (target) and `SHOTLOGFIXER_SMOKE_RECORDER` (reference) to deterministic fixture paths before running the command; it drives the real Analyse button, checks the post-commit UI and, with `SHOTLOGFIXER_SMOKE_OUTPUT_DIR`, writes a QC TXT and a corrected copy through the engine. For controlled isolation runs, pass `--isolation=header-only`, `--isolation=no-table`, `--isolation=no-timeline`, or `--css=minimal` after the Electron entry point. Diagnostics are opt-in with `--renderer-diagnostics`; normal `electron .` runs stay quiet and packaged builds do not enable them.

## Format profiles

Both inputs are interpreted through versioned format profiles (delimiter, header mode, skipped rows, encoding, and the FFID / X / Y columns by index). Before analysis the engine deterministically detects a profile for each file; delimiter, header mode, encoding, canonical mapping, validation counts, and a SHA-256 profile hash are returned in `input_formats`; `detect_format` is available through the same JSON boundary for preview/configuration. Built-in EIVA CSV, Recorder header, and headerless comma Pronav profiles are read-only conveniences that run through the same generic parser, while user profiles are stored as local JSON under `%APPDATA%\ShotLogFixer\profiles\format-profiles.json`. A profile's stored slot (`RECORDER` / `EIVA`) selects its column roles and, through `WORKFLOW_ROLE`, its workflow role (reference / target). The reference FFID must be an integer; the target's FFID is only a diagnostic, so any text is accepted there. QC TXT includes an `[INPUT_FORMATS]` provenance section.

## Engine JSON adapter

The adapter reports version `0.5.0` in its structured response and can be called directly with JSON on stdin:

```text
python -m shotlogfixer.engine_cli
```

It accepts `analyse`, `export_qc`, `save_corrected_target` (alias `save_fixed_eiva`), `detect_format`, `preview_format` and the profile actions, using `reference_path` / `target_path` (and `reference_profile` / `target_profile`); the former `recorder_*` / `eiva_*` keys are accepted as aliases. `save_fixed_pair` was removed: the recorder is never rewritten. Responses are structured JSON and never expose tracebacks. `analyse` returns the acquisition-ordered `records` (association and QC as separate fields), the `qc` findings, the `correction` summary with its `blockers`, structural `validation`, input hashes and the format provenance. Set `SHOTLOGFIXER_PYTHON` when the development interpreter is not on `PATH`. A packaged build provides the PyInstaller sidecar through the same main-process boundary.

Corrected output is fail-closed: it is written only when no structural blocker exists and the corrected copy passes independent validation (FFIDs come from the reference in reference order, no field other than the FFID changed, structure preserved, one-to-one and order preserving). Existing outputs require explicit overwrite confirmation, and both input files are SHA-256 checked before and after the write.

The existing Tkinter application (`python app.py`) remains available as a fallback; it uses the same engine.
