# TASK-004 — Milestone release verification

## Objective
Verify that the accepted baseline builds and runs as the end-user product: full regression green and a portable
Windows build produced and launched.

## Scope
- On a Windows machine with Python 3.11+ and Node 18+ (the CTO's device; this cannot run in a Linux cloud container):
  - `py -m pytest` with `SHOTLOGFIXER_REAL_DIR` pointing at the OS_A-2 sample if available (so the 7 real-sample tests
    run instead of skipping).
  - From `desktop/`: `npm ci`, `npm run typecheck`, `npm run test`, `npm run electron:smoke` with
    `SHOTLOGFIXER_SMOKE_EIVA`, `SHOTLOGFIXER_SMOKE_RECORDER` and `SHOTLOGFIXER_SMOKE_OUTPUT_DIR` set to golden scenario 3.
  - `npm run package:portable`, then launch `release/ShotLogFixer-Portable.exe`, analyse golden scenario 3, save the
    corrected copy and export QC.
- Record results (commit, pass/skip counts, artifact size and SHA-256) in PROJECT_STATUS.md.

## Non-goals
- No code changes. Any failure becomes a new task, not a fix inside this one.
- No installer, signing or auto-update work.

## Relevant components/files
- `scripts/build-portable.ps1`, `packaging/engine_entry.py`, `desktop/package.json`, `README.md` (build section).

## Acceptance criteria
- All Python and desktop tests pass; real-sample tests ran (or the report states the sample was unavailable).
- Smoke run passes and writes a QC TXT and a corrected copy.
- Portable exe starts without system Python/Node, produces the same corrected FFID column as golden scenario 3's
  `expected.json`, and leaves both inputs byte-identical.
- PROJECT_STATUS.md records the verified commit and artifact hash.

## Required tests
The full milestone set listed in Scope.

## Dependencies
TASK-001, TASK-002, TASK-003, and the default-branch decision in PROJECT_STATUS.md (Blockers).
