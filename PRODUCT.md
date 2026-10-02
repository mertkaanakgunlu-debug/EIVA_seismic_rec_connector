# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop Electron application with a native Windows shell and a React renderer.

## Stack

Electron, React, TypeScript, Vite, local compact UI primitives, and the existing Python domain engine. The release renderer uses a stable native table path.

## Users

Single-user seismic/QC operators on a survey vessel who need to correct an EIVA navigation log against the authoritative recorder log and inspect what looks unusual.

## Product Purpose

ShotLogFixer reconciles a recorder log (reference, authoritative) with an EIVA log (target) offline: every valid recorder record is associated with one EIVA row, the recorder FFID is written onto that row in a corrected copy of the EIVA file, and unassociated EIVA rows are removed. QC is a separate system that surfaces record, spacing and association anomalies in acquisition order and exports an audit TXT. Success means an operator can select two files, provide the shot interval, analyse them quickly, inspect problem regions, and save a trustworthy corrected copy without the recorder or original EIVA file ever being modified.

## Positioning

A compact offline engineering utility whose generic format layer, directional ordered one-to-one alignment, QC and audit export remain in Python while the desktop UI makes the result fast to inspect.

## Operating Context

The application runs as a single desktop window on Windows, often in a survey-vessel workflow with local files and no network dependency. The acquisition timeline, problem navigation, QC table, and TXT audit export are the primary inspection rituals.

## Capabilities and Constraints

Preserve the recorder-authoritative model (docs/recorder-authority-model.md): the recorder is the reference and is never modified; the EIVA file is the correction target; matching is recorder -> EIVA, spatial proximity first (full-precision coordinates), then one-to-one and acquisition order, with sequence continuity as tie-breaker and anomaly fallback, and no assumed row lag; distance is a QC and confidence signal, never an existence test; correction blockers (structural impossibilities) and QC warnings are separate concepts. Parsing stays generic and profile-driven. Keep the Tkinter UI available as fallback. Source logs remain read-only.

## Brand Commitments

The product name is ShotLogFixer. The visual direction is a compact professional engineering utility: dense but readable, flat, quiet, and information-first. Avoid dashboard cards, decorative widgets, marketing animation, and simulated macOS controls.

## Evidence on Hand

The regression sample is `OS_A-2_LOG.txt` (EIVA, 6,769 rows) with `OS_A-2_pronav.txt` (recorder, 6,764 records, FFID 101 to 6873, last record about 210 m off the track). 6,762 recorder records are assigned one-to-one and in order, each on the EIVA row at its position (none more than 2.4 m away), the corrected EIVA copy has 6,762 rows, 7 EIVA rows are removed, and two recorder records have no EIVA row: FFID 2525 (recorded 0.4 m from FFID 2526 where the EIVA log has one row) and FFID 6873 (a 210 m position jump, beyond the end of the EIVA log). Both are reported as `Blocked` with a severe QC finding that prices the alternative (see `tests/test_real_sample.py`; real data is not committed). The earlier OS_A-1 baseline (2816 EIVA rows, 2814 recorder rows) predates this model and was recorded under the former tolerance-based matching.

## Product Principles

- Preserve the Python engine as the source of truth.
- Keep the correction decision and the QC observation visibly separate.
- Make every inspection action quick and acquisition-order aware.
- Prefer compact density and calm hierarchy over dashboard decoration.
- Keep serious errors visible and actionable.
- Keep offline behavior and auditability explicit.

## Accessibility & Inclusion

Use keyboard-focusable controls, visible focus states, sufficient contrast in light and dark themes, semantic labels, and theme-aware scrollbars.
