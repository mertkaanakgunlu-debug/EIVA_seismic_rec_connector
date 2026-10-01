# ShotLogFixer Phase 1

Offline tkinter QC utility comparing an EIVA navigation CSV/TXT log with a whitespace-delimited seismic recorder header. It uses only `E(Spark), N(Spark)` against `SOU_X, SOU_Y` in acquisition order; FFID and timestamps are retained for audit but never used as matching keys. Matches use Euclidean distance with a 1.0 m tolerance. `MATCHED`, `EIVA_ONLY`, `RECORDER_INVALID`, and `REVIEW` describe the QC result. Source files are never modified.

Run the GUI with `python app.py`. Run tests with `pytest`. Build on Windows with `pyinstaller --onefile --windowed app.py`.

The GUI provides a horizontally scrollable, acquisition-order timeline with clickable problem markers. EIVA-only, recorder-invalid, and review counters support wrapped previous/next navigation. The default table shows FFIDs, coordinate pairs, distance, and status; optional raw EIVA columns and diagnostics can be enabled with **Columns**. CSV export always retains the complete audit fields regardless of table visibility.
