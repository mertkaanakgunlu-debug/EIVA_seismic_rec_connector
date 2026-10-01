# ShotLogFixer Phase 1

Offline tkinter QC utility comparing an EIVA navigation CSV/TXT log with a whitespace-delimited seismic recorder header. It uses only `E(Spark), N(Spark)` against `SOU_X, SOU_Y` in acquisition order; FFID and timestamps are retained for audit but never used as matching keys. Matches use Euclidean distance with a 1.0 m tolerance. `MATCHED`, `EIVA_ONLY`, `RECORDER_INVALID`, and `REVIEW` describe the QC result. Source files are never modified.

Run the GUI with `python app.py`. Run tests with `pytest`. Build on Windows with `pyinstaller --onefile --windowed app.py`.
