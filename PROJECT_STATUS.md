# Project Status

_Last updated: 2026-10-02 (bootstrap)_

## Validated baseline
- Commit `7ef755d3adb1b6010233d61619f5342d7917ec9b` on branch `phase5-recorder-authoritative-alignment`
  (ShotLogFixer 0.5.0). History is linear from `e071a04`; every older `phase*`, `runtime-*` and `ui-*` branch is an
  ancestor of this commit.
- Last accepted commit: `7ef755d` (bootstrap baseline; no task accepted yet).

## Completed capabilities (at baseline)
- Generic, profile-driven parsing of recorder and EIVA text files with deterministic format detection and local user
  profiles (`format_*`, `table_parser`, `canonical_mapping`).
- Recorder → EIVA ordered one-to-one alignment by full-precision coordinates plus sequence continuity (exact DP with a
  corridor fallback for large slack); EIVA FFIDs never decide identity (`alignment.py`).
- QC separate from correction: recorder, target and association findings with severities (`qc.py`).
- Correction: corrected copy of the EIVA file with recorder FFIDs, unassigned rows removed, everything else preserved;
  fail-closed structural validation; inputs hash-checked; never overwritten (`correction.py`, `validation.py`).
- QC audit TXT export (`report.py`); JSON engine boundary (`engine_cli.py`).
- Electron/React desktop UI (`desktop/`), legacy Tkinter fallback (`app.py`), portable Windows build script.
- The 104 → 105 / ~207 FFID-divergence scenario matches correctly by coordinates (checked with a synthetic run at
  bootstrap); QC shows it only indirectly (TASK-002).

## Active task
None.

## Queued tasks (in order)
1. [TASK-001](tasks/TASK-001-golden-regression-dataset.md) — compact golden regression dataset (tests only).
2. [TASK-002](tasks/TASK-002-qc-ffid-divergence.md) — explicit QC finding for FFID divergence. Depends on 001.
3. [TASK-003](tasks/TASK-003-release-verification.md) — milestone release verification on Windows. Depends on 001, 002.

Strictly sequential: 002 updates 001's golden expectations, and 003 verifies both.

## Known blockers / open decisions
- **Verbatim Project Goal and Project Instructions not yet supplied**; PROJECT_GOAL.md / PROJECT_INSTRUCTIONS.md hold
  only the CTO's bootstrap rules. Once supplied, check the baseline model (recorder authoritative; order is a hard
  constraint that can place a run one row from the spatially nearest row, flagged by QC as
  `ASSOCIATION_NEAREST_OVERRIDDEN` / `ASSOCIATION_RUN_DISPLACED`) against it; any conflict becomes a task.
- **Default branch is stale**: GitHub's default branch is `phase1-detection-qc` (`645a049`, 15 commits behind the
  baseline). Needs a CTO decision before TASK-003: fast-forward a `main` branch to the baseline and make it the default.
- 13 superseded remote branches remain (all ancestors of the baseline); safe to delete once the default branch is fixed.

## Test / build status (at baseline, Linux cloud container)
| Suite | Command | Result | Time |
|---|---|---|---|
| Python | `python -m pytest` | 150 passed, 7 skipped (real OS_A-2 sample absent) | ~2 s |
| Python, parallel | `python -m pytest -n auto` | same | ~2 s (no gain) |
| Desktop unit | `npm run test` (in `desktop/`) | 11 passed | ~1 s |
| Desktop types | `npm run typecheck` | clean | ~4 s |
| Electron smoke / portable build | Windows only | not run | — |

No test-suite bottleneck: the slowest test is ~0.8 s. Tests use `tmp_path` and `ProfileStore(tmp_path/...)`, so they
are parallel-safe, but xdist is not worth enabling at this size. No CI workflow exists.
