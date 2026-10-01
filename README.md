# ShotLogFixer 0.4.0

Offline QC utility comparing an EIVA navigation CSV/TXT log with a whitespace-delimited seismic recorder header. It uses only `E(Spark), N(Spark)` against `SOU_X, SOU_Y` in acquisition order; FFID and timestamps are retained for audit but never used as matching keys. The operator supplies the nominal shot interval; matching uses Euclidean distance with the derived half-interval tolerance. `MATCHED`, `EIVA_ONLY`, `NO_SHOT`, `RECORDER_INVALID`, and `REVIEW` describe record-level QC, while Recorder spatial gaps are separate geometry events. Source files are never modified.

Run the GUI with `python app.py`. Run tests with `pytest`. Build the portable Windows release with `npm run package:portable` from `desktop/`. The result is `release/ShotLogFixer-Portable.exe`; it bundles the Python engine and does not require system Python or Node at runtime.

The GUI provides a horizontally scrollable, acquisition-order timeline with clickable problem markers. The issue counters use readable labels such as **EIVA only**, **Not recorded**, **Invalid**, and **Review**; FFID jumps are summarized by count and individual transitions appear when a jump is inspected. The default table shows FFIDs, coordinate pairs, distance, and status; optional raw EIVA columns and diagnostics can be enabled with **Columns**. QC TXT export retains readable labels together with canonical code columns regardless of table visibility. The footer shows the packaged application version.

## Electron/React desktop UI

The migration candidate lives in `desktop/`. Electron owns native file dialogs, Python process execution, path validation, and QC export. The React renderer communicates through a narrow preload bridge; it has no Node integration or unrestricted filesystem access. The Python parser, matcher, QC helpers, and report writer remain the authoritative domain engine.

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

The renderer keeps the compact Phase 2 layout and canvas acquisition timeline. The table uses a stable native render path: the former TanStack table/virtualizer combination was isolated as the source of an unbounded Windows Chromium render loop (it reproduced with zero rows and after both theme and analysis updates), so it is no longer on the release path. Development-only diagnostics record Electron renderer lifecycle events, a renderer heartbeat, React render counters, theme phases, analysis IPC/Python/JSON timings, response size and raw-field contribution, and post-commit animation frames. Production builds do not emit those diagnostics. Theme selection remains a controlled menu backed by CSS variables and persisted preference.

To run the diagnostic smoke test, use `npm run electron:smoke`. It clicks the real ThemePicker and Columns controls, waits for two animation frames after each theme change, and verifies heartbeat progress. An analysis smoke pass can be added by setting `SHOTLOGFIXER_SMOKE_EIVA` and `SHOTLOGFIXER_SMOKE_RECORDER` to deterministic fixture paths before running the command; it drives the real Analyse button and checks the post-commit UI. For controlled isolation runs, pass `--isolation=header-only`, `--isolation=no-table`, `--isolation=no-timeline`, or `--css=minimal` after the Electron entry point. Diagnostics are opt-in with `--renderer-diagnostics`; normal `electron .` runs stay quiet and packaged builds do not enable them.

The adapter reports version `0.4.0` in its structured response. Before analysis it deterministically detects a versioned input format profile for each file. Delimiter, header mode, encoding, canonical FFID/X/Y mapping, validation counts, and a SHA-256 profile hash are returned in `input_formats`; `detect_format` is available through the same JSON boundary for preview/configuration. Built-in EIVA CSV, Recorder header, and headerless comma Pronav profiles are read-only, while user profiles are stored as local JSON under `%APPDATA%\ShotLogFixer\profiles\format-profiles.json`. QC TXT includes an `[INPUT_FORMATS]` provenance section. The adapter can also be called directly with JSON on stdin:

```text
python -m shotlogfixer.engine_cli
```

It accepts `analyse`, `export_qc`, `save_fixed_eiva`, and `save_fixed_pair` actions and returns structured JSON errors without exposing tracebacks to the UI. Set `SHOTLOGFIXER_PYTHON` when the development interpreter is not on `PATH`. A packaged build can provide the future PyInstaller sidecar through the same main-process boundary.

## Phase 2 correction

After analysis, ShotLogFixer classifies recorder rows as `VALID`, `NO_SHOT` (the complete `-214748.36480` sentinel pair), or `INVALID`. It builds a deterministic correction plan from the existing coordinate/order matcher. EIVA-only rows and safely bracketed no-shot navigation rows are removed; retained EIVA FFIDs are replaced with their matched recorder FFIDs. Ambiguous intervals, boundary no-shots, invalid rows, and unresolved review rows block output.

The operator supplies `shot_interval_m`; Python derives `match_tolerance_m = shot_interval_m / 2` and uses that value for matching and both validation passes. Fixed EIVA and recorder coordinates are formatted to exactly two decimal places while unrelated fields and source row order are preserved. **Save Fixed EIVA** writes one validated navigation file; **Save Fixed Pair** writes `<eiva-stem>_fixed.txt` and `<recorder-stem>_fixed.txt` as one validated operation. Existing outputs require explicit overwrite confirmation, and raw input files are SHA-256 checked and never modified.

Correction is fail-closed: the Python writer refuses to write unless both the in-memory pair and its serialized two-decimal representation pass independent validation. Analysis remains available without saving, and a failed validation writes nothing.

The existing Tkinter application remains available with `python app.py` as a fallback/reference during acceptance.

## Phase 3 geometry QC

Recorder spatial gaps are separate acquisition-geometry events. Consecutive valid Recorder anchors are candidates only when their coordinate distance is at least `recorder_gap_threshold_m = 5 * shot_interval_m`; span steps are `round(distance / shot_interval_m)` and estimated missing intermediate positions are `span - 1`. The right anchor is never counted as missing, FFID differences are never used to estimate geometry, and explicit `NO_SHOT` rows are deducted from the unexplained metric. Shared and deterministic EIVA-only gaps remain warning-only; invalid, off-slot, or non-unique mappings are classified `RECORDER_GAP_AMBIGUOUS` and block correction. QC TXT includes interval, matching tolerance, gap threshold, per-record attribution, and a `[RECORDER_GAPS]` audit section.
