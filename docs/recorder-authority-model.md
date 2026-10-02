# Recorder-authoritative reconciliation

ShotLogFixer reconciles a seismic **recorder log** with an **EIVA/navigation log**. The workflow is deliberately
asymmetric, while the format layer stays generic (any supported text file, configurable delimiter, header, encoding,
skipped rows and FFID / X / Y columns, reusable profiles).

| Workflow role | Typical file | Meaning |
|---|---|---|
| **Reference** | seismic recorder log | Authoritative. A valid row means that shot really exists, its FFID is the authoritative FFID, its coordinate is the primary spatial reference. Never modified. |
| **Target** | EIVA / navigation log | The dataset being corrected. Its own FFIDs are diagnostics only and never decide shot identity. |

Profile slots keep their stored names (`RECORDER` = reference, `EIVA` = target; see `WORKFLOW_ROLE` in
`format_profiles.py`). Everything downstream of parsing works on role-tagged `SourceRecord` objects: there is one
alignment engine, no vendor-specific matching.

## What changed (and why the old flow was wrong)

Before this change the pipeline was `match_records` (greedy cursor matcher) -> `build_correction_plan` -> `analyse_recorder_gaps`
-> `validate_candidates`. It treated distance as an existence test and let QC decide correction:

| Where | Assumption that conflicted with Recorder authority |
|---|---|
| `matcher.py` | `distance <= shot_interval / 2` was a hard rejection: a valid recorder record farther away had no candidate and became `REVIEW` (never assigned). |
| `matcher.py` | Greedy forward cursor: the first acceptable candidate won and could never be revised; an ambiguous pair became `REVIEW`; a recorder row with no nearby EIVA row opened an "uncertainty window" that relabelled EIVA rows. |
| `correction.py` | Any recorder `REVIEW`, any `INVALID` row and any recorder-gap ambiguity blocked the corrected copy: QC outcomes redefined correction truth. |
| `gap_analysis.py` | A gap classified `RECORDER_GAP_AMBIGUOUS` set `blocks_correction`. |
| `validation.py` | `coordinate_pass_count != len(keep)` ("coordinates fail the tolerance") blocked output; the pair also had to have equal rows and two-decimal coordinates. |
| `correction.py` | Retained EIVA coordinates were rewritten with `:.2f` (an unrelated field changed) and a modified recorder copy was written ("fixed pair"). |
| `canonical_mapping.py` | A target row with unreadable coordinates aborted the whole analysis; target FFIDs had to be integers. |
| UI | "Matched / EIVA only / Review" conflated QC findings with the correction decision. |

## The model

1. **Normalise** both inputs through their format profiles into `SourceRecord` (`canonical_mapping.map_records`). Rows that
   cannot be read are kept, classified and reported (`INVALID`, or `NO_SHOT` for the recorder sentinel pair), never fatal.
2. **Align** every valid reference record to a target row (`alignment.align_records`), directional and ordered.
3. **QC** (`qc.run_qc`) reads the records and the alignment and reports observations. It cannot change an association.
4. **Correct** (`correction.build_correction_plan`): the reference FFID replaces the mapped FFID on every associated target row;
   unassociated target rows are removed; every other byte of the target file is preserved. Only structural impossibilities
   are blockers.

### Alignment

Reference rows `R[0..m-1]` and target rows `T[0..n-1]` are ordered acquisition sequences. A valid assignment is a strictly
increasing map `f: R -> T` (one-to-one, order preserving): `f(i) = i + d_i` with offsets `0 <= d_0 <= ... <= d_{m-1} <= n - m`.

The cost minimised exactly, by dynamic programming over the offsets (`m x (n - m + 1)` states):

* **spatial**: full-precision distance `|R[i] - T[f(i)]|`, saturating at `cap = 5 x shot interval`. Beyond `cap` a coordinate
  no longer prefers one candidate over another, so one anomalous coordinate cannot drag its neighbours; sequence decides.
  A target row without a usable position costs `cap`. Nothing is ever rejected.
* **sequence continuity**: one nanometre per place where the offset increases (a run of target rows is skipped). It only
  breaks ties, preferring the most continuous assignment with skips as late as possible.

Properties: one-to-one and monotone by construction; deterministic (integer costs); optimal (verified against an exhaustive
oracle in `tests/test_alignment.py`); every valid reference record is assigned whenever `n >= m`. Competing placements are
detected with forward/backward min-marginals and reported as ambiguity. For very large slack the search is restricted to a
corridor around a robust spatial trajectory (longest non-decreasing chain of nearest-row offsets); it equals the exact
result on the tested instances. If the target has fewer rows than there are valid reference records, no complete assignment
exists: the shorter side is embedded for display, the unplaced records are reported as `BLOCKED` and correction is blocked.

### Correction blockers vs QC warnings

| Correction blockers (structural, stop the corrected copy) | QC findings (never block) |
|---|---|
| recorder rows that cannot be interpreted (`REFERENCE_ROWS_INVALID`) | large / severe association distance |
| no valid recorder record, or no target row | recorder position jump / spike, abnormal spacing |
| fewer target rows than valid recorder records (`INSUFFICIENT_TARGET_ROWS`) | FFID gap, reversal, duplicate |
| an associated target row has no FFID field to write | ambiguous or sequence-only association |
| the corrected copy fails structural validation | target-only rows, unreadable target rows, no-shot rows |

### Result rows

Each result row carries a **correction decision** (`association`: `ASSIGNED`, `TARGET_ONLY`, `INVALID`, `NO_SHOT`, `BLOCKED`) and,
separately, a **QC status** (`OK`, `INFO`, `WARNING`, `SEVERE`) with its codes. A recorder record whose coordinate jumps 200 m is
`ASSIGNED` with QC `SEVERE`, never "unmatched".

### Invariants

Recorder FFID and shot existence are authoritative; the recorder is never corrected; the target is the correction target;
matching is recorder -> target; full-precision coordinates and sequence continuity both participate; assignment is
one-to-one; large distance creates QC, not deletion; corrected FFIDs come from the recorder; unassigned target rows are
removed; QC warnings and correction blockers are different concepts.

## Known limitations

* Order is a hard constraint. A recorder record with no counterpart in the target (or an extra target row that must
  absorb it) forces a run of associations one row away from the spatially nearest row until slack absorbs it. QC reports such runs
  (`ASSOCIATION_RUN_DISPLACED`); the assignment is still the minimum-cost one-to-one ordered one.
* A systematic along-track offset between the logs larger than half a shot interval is not estimated or compensated; it shows
  as elevated association distances.
* Recorder rows that cannot be interpreted block correction (they can be neither assigned nor safely discarded).
