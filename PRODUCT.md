# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop Electron application with a native Windows shell and a React renderer.

## Stack

Electron, React, TypeScript, Vite, local compact UI primitives, and the existing Python domain engine. The release renderer uses a stable native table path.

## Users

Single-user seismic/QC operators on a survey vessel who need to inspect an EIVA navigation log against a recorder header log.

## Product Purpose

ShotLogFixer performs offline coordinate matching and QC review for two acquisition logs, surfaces record and geometry anomalies in acquisition order, and exports an audit TXT. Success means an operator can select two files, provide the shot interval, analyse them quickly, inspect problem regions, and retain the accepted correction semantics.

## Positioning

A compact offline engineering utility whose authoritative parser, monotonic matcher, uncertainty handling, and audit export remain in Python while the desktop UI makes the result fast to inspect.

## Operating Context

The application runs as a single desktop window on Windows, often in a survey-vessel workflow with local files and no network dependency. The acquisition timeline, problem navigation, QC table, and TXT audit export are the primary inspection rituals.

## Capabilities and Constraints

Preserve EIVA parsing, recorder parsing, acquisition-order matching, operator-derived half-interval tolerance, ambiguity safeguards, uncertainty propagation, FFID discontinuity reporting, geometry-event grouping, and QC TXT semantics. Keep the Tkinter UI available as fallback during migration. Source logs remain read-only.

## Brand Commitments

The product name is ShotLogFixer. The visual direction is a compact professional engineering utility: dense but readable, flat, quiet, and information-first. Avoid dashboard cards, decorative widgets, marketing animation, and simulated macOS controls.

## Evidence on Hand

The accepted real-data baseline is documented in the migration specification and uses `C:\Users\mertk\Downloads\OS_A-1_LOG_EIVA.txt` and `C:\Users\mertk\Downloads\OS-A-1_header.txt` when available. Accepted counts are 2816 EIVA rows, 2814 recorder rows, 2813 MATCHED, 2 EIVA_ONLY, 1 RECORDER_INVALID, 1 REVIEW, 2 issue regions, and FFID discontinuity 543 to 553.

## Product Principles

- Preserve the Python engine as the source of truth.
- Make every inspection action quick and acquisition-order aware.
- Prefer compact density and calm hierarchy over dashboard decoration.
- Keep serious errors visible and actionable.
- Keep offline behavior and auditability explicit.

## Accessibility & Inclusion

Use keyboard-focusable controls, visible focus states, sufficient contrast in light and dark themes, semantic labels, and theme-aware scrollbars.
