# Project Instructions

> **Status: verbatim Project Instructions not yet supplied.**
> The Cloud Project's Instructions field was empty at bootstrap (2026-10-02). When the CTO supplies the text, it
> replaces the "Pending" section below verbatim. The operating rules after it come from the CTO's bootstrap message and
> stay in force unless the supplied text changes them. Do not silently weaken or expand either.

## Pending: verbatim Project Instructions

_(to be pasted exactly as supplied by the CTO)_

## Operating rules (CTO bootstrap message, 2026-10-02)

### Source of truth
- [PROJECT_GOAL.md](PROJECT_GOAL.md) is authoritative for product behaviour.
- The repository is the technical source of truth unless it conflicts with PROJECT_GOAL.md or explicit CTO instructions.
- Do not redesign working architecture merely because an alternative design is possible.

### Work happens through tasks
- All implementation work is defined by a task file in [tasks/](tasks/), named `TASK-NNN-short-title.md`, using the
  template in [tasks/README.md](tasks/README.md).
- One coherent behavioural change per task. No mega-tasks, no speculative work, no scope expansion.
- Tasks reference canonical documents instead of repeating them.

### Orchestrator workflow for `Implement TASK-NNN`
1. Read the task.
2. Read only the canonical context and repository areas that task needs.
3. Check that its dependencies are satisfied (see [PROJECT_STATUS.md](PROJECT_STATUS.md)).
4. Hand it to one implementation thread with only: the task file, PROJECT_GOAL.md, PROJECT_INSTRUCTIONS.md,
   PROJECT_STATUS.md. No long history, no whole-repository rediscovery.
5. The thread implements only the authorized scope.
6. The thread runs the task's targeted tests.
7. Inspect the result against the task's acceptance criteria.
8. Request revision if any criterion is unmet.
9. Accept only after verification.
10. Update PROJECT_STATUS.md.

### Implementation threads
- Work on a branch from the current validated baseline (PROJECT_STATUS.md) and open a PR into it.
- Touch only files the task names, plus tests. If the task cannot be done within its scope, stop and report rather than
  widening it.
- Report: what changed, which tests ran with their result, and each acceptance criterion as met / not met.

### Testing levels
| When | What to run |
|---|---|
| During implementation | Targeted tests for the affected component (e.g. `python -m pytest tests/test_qc.py`). |
| Task completion | The module / regression tests the task lists, plus the golden dataset tests once they exist. |
| Milestone / final closure | Full regression (Python + desktop) and packaging / build verification. |

Full command set (all fast; see PROJECT_STATUS.md for timings):
- Python: `python -m pytest` from the repository root (`-n auto` with pytest-xdist is safe but gives no benefit at the
  current suite size).
- Desktop: from `desktop/`, `npm run typecheck` and `npm run test`.
- Milestone only: `npm run electron:smoke` and `npm run package:portable` (Windows).

Prefer small deterministic synthetic fixtures and the compact golden dataset over large survey files. Real survey data
is never committed.

### Domain guardrails
See PROJECT_GOAL.md. In particular: keep matching, QC, and correction separate; coordinates are primary matching
evidence; FFID/sequence divergence is QC evidence and never overrides a strong coordinate match; correction only under
explicit rules; never overwrite input files.

### Product simplicity
The product stays an easy-to-run offline desktop utility. Project orchestration is for the development workflow only
and never enters the product.

### PROJECT_STATUS.md
Current state only, kept short: validated baseline, capabilities, active and queued tasks, blockers, test/build status,
last accepted commit. It is not a diary.
