# ShotLogFixer Phase 1

Offline tkinter QC utility comparing an EIVA navigation CSV/TXT log with a whitespace-delimited seismic recorder header. It uses only `E(Spark), N(Spark)` against `SOU_X, SOU_Y` in acquisition order; FFID and timestamps are retained for audit but never used as matching keys. Matches use Euclidean distance with a 1.0 m tolerance. `MATCHED`, `EIVA_ONLY`, `RECORDER_INVALID`, and `REVIEW` describe the QC result. Source files are never modified.

Run the GUI with `python app.py`. Run tests with `pytest`. Build on Windows with `pyinstaller --onefile --windowed app.py`.

The GUI provides a horizontally scrollable, acquisition-order timeline with clickable problem markers. EIVA-only, recorder-invalid, and review counters support wrapped previous/next navigation. The default table shows FFIDs, coordinate pairs, distance, and status; optional raw EIVA columns and diagnostics can be enabled with **Columns**. CSV export always retains the complete audit fields regardless of table visibility.

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

The renderer keeps the compact Phase 2 layout while using a virtualized QC table and a canvas acquisition timeline. Development-only performance marks cover theme changes, analysis response/state assignment, table rendering, and timeline rendering; production builds do not emit those diagnostics. Theme selection is a controlled menu backed by CSS variables and persisted preference, without runtime `color-scheme` switching.

The adapter can also be called directly with JSON on stdin:

```text
python -m shotlogfixer.engine_cli
```

It accepts `analyse`, `export_qc`, `save_fixed_eiva`, and `save_fixed_pair` actions and returns structured JSON errors without exposing tracebacks to the UI. Set `SHOTLOGFIXER_PYTHON` when the development interpreter is not on `PATH`. A packaged build can provide the future PyInstaller sidecar through the same main-process boundary.

## Phase 2 correction

After analysis, ShotLogFixer classifies recorder rows as `VALID`, `NO_SHOT` (the complete `-214748.36480` sentinel pair), or `INVALID`. It builds a deterministic correction plan from the existing coordinate/order matcher. EIVA-only rows and safely bracketed no-shot navigation rows are removed; retained EIVA FFIDs are replaced with their matched recorder FFIDs. Ambiguous intervals, boundary no-shots, invalid rows, and unresolved review rows block output.

The engineering tolerance is 1.0 m using full parsed precision. Fixed EIVA and recorder coordinates are formatted to exactly two decimal places while unrelated fields and source row order are preserved. **Save Fixed EIVA** writes one validated navigation file; **Save Fixed Pair** writes `<eiva-stem>_fixed.txt` and `<recorder-stem>_fixed.txt` as one validated operation. Existing outputs require explicit overwrite confirmation, and raw input files are SHA-256 checked and never modified.

Correction is fail-closed: the Python writer refuses to write unless both the in-memory pair and its serialized two-decimal representation pass independent validation. Analysis remains available without saving, and a failed validation writes nothing.

The existing Tkinter application remains available with `python app.py` as a fallback/reference during acceptance.
