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

### Alignment: spatial proximity first

Evidence, strongest first:

| Signal | Role |
|---|---|
| **Spatial proximity** | The primary association signal. Full-precision distance `\|R[i] - T[j]\|`; the candidates for a recorder record are the target rows within `cap = 5 x shot interval`, and the closer the better. It ranks candidates and is never an existence test. |
| **One-to-one** | Mandatory. A target row belongs to at most one recorder record. |
| **Acquisition order** | A consistency constraint: associations never cross. It is *not* a lag model. Nothing assumes a stable row offset between the two logs. |
| **Sequence context** | Tie-breaker and anomaly fallback: a record without usable spatial evidence (anomalous coordinate, target row without a position) takes the free target rows between its associated neighbours, and exact ties go to the earliest row. |
| **QC** | Reports unusual gaps and distances. Never redefines the correction. |

So a recorder outage is not a special case. If FFID 104 sits on target row 104 and FFID 105 (after a ten minute outage, while the
navigation log kept running) sits on target row 207, FFID 105 is associated with row 207 because that row is at its position.
The 102 rows between them cost nothing, are unassigned, and are removed from the corrected copy. The EIVA FFID is never consulted.

**Objective.** Each candidate pair has the gain `cap - distance` (distances saturate at `cap`: beyond it a coordinate stops
preferring one row over another). The alignment is the strictly increasing chain of pairs, in both reference and target order,
with the largest total gain. That is the assignment of minimum total cost when a recorder record on row *j* costs
`min(distance, cap)` and an unassigned record costs `cap`. It is found exactly by a weighted longest-chain dynamic programme over
the candidate pairs (`O(P log n)`), with no band, window or lag, so a stretch of unused target rows of any length costs nothing.
Costs are integers (1 unit = 1 nm), so ties break deterministically, to the earliest target rows.

**Sequence fallback.** Records the chain leaves out take the free target rows between their chained neighbours, left to right
(basis `SEQUENCE`; flagged ambiguous when more free rows than records exist). This is how an anomalous recorder coordinate, such
as the 210 m jump in the last record of the sample, still receives its row whenever one is free.

Properties: one-to-one and order preserving by construction; deterministic; optimal against an exhaustive oracle for the
documented cost (`tests/test_alignment.py`); ambiguity from forward/backward min-marginals; every candidate pair is found with a
grid index, so the cost grows with the number of nearby pairs and not with the length of the logs.

### Recorder records without a target row

A recorder record stays unassigned only when no free target row lies between its associated neighbours, i.e. when giving it a row
would take a better-fitting row away from another record. Insisting that every record keeps a row moves every record between it and
the nearest unused target row onto a row that fits it worse. On the OS_A-2 sample that is the difference between
two unassigned records (FFID 2525, recorded 0.4 m from FFID 2526 where the EIVA log has a single row, and FFID 6873, beyond the end
of the EIVA log) and 1,452 correct associations (236 + 1,216) pushed one row off their position, adding about 2.8 km of distance.

Such a record is **not silently dropped**: it remains in the result with status `BLOCKED`, a `SEVERE` QC finding
`ASSOCIATION_BLOCKED` names the rival that holds its nearest row and prices the alternative ("would move the next 236 recorder
records one target row later, adding 742 m"), and the summary counts it. It is absent from the corrected copy because there is no
target row to renumber, but it never blocks the copy.

### Correction blockers vs QC warnings

| Correction blockers (structural, stop the corrected copy) | QC findings (never block) |
|---|---|
| recorder rows that cannot be interpreted (`REFERENCE_ROWS_INVALID`) | large / severe association distance |
| no valid recorder record, or no target row | recorder position jump / spike, abnormal spacing |
| fewer target rows than valid recorder records (`INSUFFICIENT_TARGET_ROWS`) | FFID gap, reversal, duplicate |
| an associated target row has no FFID field to write | ambiguous or sequence-only association |
| the corrected copy fails structural validation | a recorder record no target row can hold (`ASSOCIATION_BLOCKED`), target-only rows, unreadable target rows, no-shot rows |

### Result rows

Each result row carries a **correction decision** (`association`: `ASSIGNED`, `TARGET_ONLY`, `INVALID`, `NO_SHOT`, `BLOCKED`) and,
separately, a **QC status** (`OK`, `INFO`, `WARNING`, `SEVERE`) with its codes. A recorder record whose coordinate jumps 200 m is
`ASSIGNED` with QC `SEVERE` when a free target row exists for it, never "unmatched"; `BLOCKED` means only that no target row can hold
it, whatever its coordinate. The corrected copy holds one row for each recorder record that received a target row
(`corrected rows` of `recorder records` in the summary).

### Invariants

Recorder FFID and shot existence are authoritative; the recorder is never corrected; the target is the correction target;
matching is recorder -> target; full-precision coordinates decide first and sequence continuity second; assignment is
one-to-one; large distance creates QC, not deletion; corrected FFIDs come from the recorder; unassigned target rows are
removed; QC warnings and correction blockers are different concepts.

## Known limitations

* Order is a hard constraint, so a recorder record that no target row can hold is left unassigned rather than forced (see above).
  If the target log really does hold a row for it that the position evidence cannot place, the operator has to decide; QC states
  what making room would cost.
* A systematic along-track offset between the logs is not estimated or compensated; spatial proximity simply follows the
  positions. (In the OS_A-2 sample the recorder position of FFID *f* matches the EIVA row labelled *f* + 1.)
* Inside a stretch with no spatial evidence at all, free target rows are used left to right and flagged ambiguous; the
  position of an anomalous record among several spare rows is a guess.
* The candidate search uses the radius `cap = 5 x shot interval`. A shot interval entered orders of magnitude too large makes the
  search impractical and stops with an error that names the shot interval.
* Recorder rows that cannot be interpreted block correction (they can be neither assigned nor safely discarded).
