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

The adapter can also be called directly with JSON on stdin:

```text
python -m shotlogfixer.engine_cli
```

It accepts `analyse` and `export_qc` actions and returns structured JSON errors without exposing tracebacks to the UI. Set `SHOTLOGFIXER_PYTHON` when the development interpreter is not on `PATH`. A packaged build can provide the future PyInstaller sidecar through the same main-process boundary.

The existing Tkinter application remains available with `python app.py` as a fallback/reference during acceptance. Phase 2 correction is not implemented: this migration does not reclassify `NO_SHOT`, plan corrections, rename FFIDs, or write `_fixed.txt` output.
