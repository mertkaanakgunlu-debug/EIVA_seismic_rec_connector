# TASK-UI-002 — Compact Controls and QC Usability

## Objective

Finish the main application interface so it is compact, easy to understand and ready for normal operator use.

This task combines:

- compact input/action layout,
- low-frequency settings cleanup,
- simplified QC information hierarchy,
- human-readable QC messages,
- drag-and-drop QC column ordering.

The matching engine is frozen.

Do not change:

- matching behaviour,
- alignment rules,
- correction rules,
- QC detection rules,
- thresholds or calculations.

This is a presentation and interaction task only.

---

# 1. Compact input and action area

The current input section still uses too much vertical space.

Use this layout concept:

```text
Reference (Recorder)
[file......................................] [Browse] [⚙]      [ ANALYSE ]

Target (EIVA)                                               [ Export QC ]
[file......................................] [Browse] [⚙]      [ Save Corrected Set ]
                                                               [ Save Corrected EIVA ]
```

Exact pixel placement may adapt responsively, but preserve this structure:

### Left side

Two compact file rows:

- Reference (Recorder)
- Target (EIVA)

Each row contains:

1. file field,
2. Browse,
3. compact Configure/settings icon.

The Configure button must no longer live on a separate row.

The gear opens the existing format configuration for that specific file.

### Format status

Do not give format status its own large row.

Show it as small secondary information near/below the corresponding file field, for example:

`Pronav 3-column · Ready`

`EIVA Standard CSV · Ready`

It should be visually subordinate to the file selector.

---

# 2. Right-side action column

Keep the main actions together in one compact vertical column.

Order:

1. `ANALYSE`
2. `Export QC`
3. `Save Corrected Set`
4. `Save Corrected EIVA`

`ANALYSE` remains the visually dominant primary action.

Output actions should remain disabled until their existing readiness conditions are satisfied.

Do not change readiness logic.

## Save Corrected Set

First inspect whether `Save Corrected Set` already exists as a real product capability.

- If it already exists, expose the existing action here.
- If it does not exist, do not invent new engine/backend behaviour in this task.

If it does not currently exist, report that clearly and omit the button for now.

---

# 3. Move Shot Interval out of the main screen

Audit the current UI usage of:

- Shot Interval
- QC normal distance

The current implementation indicates Shot Interval controls QC distance bands rather than matching rejection.

Preserve all existing behaviour.

Remove these controls/readouts from the main interface.

Move them into one compact application `Settings` panel/dialog.

The Settings entry point should live in a low-noise location, preferably the application header near Theme.

Example content:

```text
Settings

QC
Shot interval          [ 3.125 ] m
Normal QC distance     1.5625 m
```

If `QC normal distance` is derived from Shot Interval, keep it read-only and clearly indicate that it is calculated.

Do not change the formula.

Do not introduce new settings.

---

# 4. Main QC summary simplification

The current summary exposes too many technical categories simultaneously.

The first-level QC summary should answer only:

1. How many shots were matched?
2. How many EIVA rows have no recorder counterpart?
3. Is there anything that needs operator review?

Prefer a compact primary summary such as:

```text
Matched          6,762
EIVA-only            7
Needs review         2
```

Use existing underlying data.

Do not change classification logic.

### Terminology

Prefer operator-facing wording:

- `Assigned` → `Matched`
- `Target-only` → `EIVA-only`
- multiple severe/warning/blocker counters → aggregate under `Needs review` where appropriate

Do not destroy or lose the detailed categories.

---

# 5. QC Details

Move secondary diagnostic categories into an expandable `QC details` / `Details` area.

Detailed information may include existing categories such as:

- Invalid
- Blocked
- QC severe
- QC warnings
- QC notes
- Recorder position jumps
- Recorder FFID jumps
- offset/discontinuity information
- no-shot rows

The operator must still be able to inspect and navigate these findings.

The change is information hierarchy only.

---

# 6. Human-readable QC text

Keep the QC notes because they are useful, but rewrite visible descriptions so an operator can understand them without knowing internal implementation terminology.

Examples:

Instead of:

`TARGET_ONLY`

show:

`EIVA position has no recorder counterpart.`

And where appropriate:

`This row will not be included in the corrected EIVA file.`

Instead of:

`RECORDER_TARGET_UNMATCHED`

show:

`Recorder FFID 6873 could not be matched to a nearby EIVA position.`

Additional detail may say:

`The nearest EIVA position is approximately 210 m away, so this recorder record was left unmatched for review.`

Instead of only:

`FFID jump`

show:

`Recorder FFID sequence jumps from 245 to 247.`

Instead of internal solver language such as:

`fits it better`

describe the observable situation.

Technical/internal codes may remain available in detailed/debug information if useful.

Do not change the underlying QC finding itself.

---

# 7. QC table column drag-and-drop

Allow users to rearrange visible QC table columns by dragging the table headers left or right.

Requirements:

- drag a column header horizontally;
- show a clear insertion indicator while dragging;
- move the complete column, header and row cells together;
- preserve existing sorting/filtering/navigation behaviour;
- do not break horizontal table scrolling;
- do not interfere with row selection;
- column widths remain stable after moving.

The result should make side-by-side coordinate/FFID comparison easier.

---

# 8. Persist column layout

Save the user's QC column order locally.

Use lightweight local persistence such as existing browser/local application storage.

No backend.

No repository file.

No engine setting.

On next application launch, restore the previous order.

Add:

`Reset columns`

to the existing Columns popover.

Reset restores the product's default column order.

Visibility selection and ordering should coexist cleanly.

---

# 9. Existing overlay system

TASK-UI-001 introduced the shared portal-based Popover/FloatingTooltip system.

Reuse it.

Do not create another floating-panel implementation.

Use the same overlay behaviour for new Settings/QC detail controls where appropriate:

- stays above the interface,
- viewport-safe,
- outside click closes,
- Escape closes.

React Bits is not currently installed.

Do not introduce React Bits or another UI dependency just for this task.

---

# 10. Compact visual hierarchy

The final main screen should prioritise:

1. choose Recorder file,
2. choose EIVA file,
3. Analyse,
4. understand the result,
5. inspect exceptions if necessary,
6. save/export outputs.

Low-frequency configuration must not dominate the screen.

Avoid:

- repeated labels,
- unnecessary vertical rows,
- large empty spaces,
- displaying every diagnostic counter at the same visual priority.

This should feel like a compact professional desktop utility.

---

# 11. Responsive behaviour

Preserve the responsive/window behaviour completed in TASK-UI-001.

At normal desktop widths:

- file controls stay left;
- action column stays right.

At narrow widths:

- controls may stack naturally;
- no overlap;
- no clipped controls;
- no inaccessible actions.

Do not regress:

- footer visibility,
- internal QC table scrolling,
- overlay positioning,
- 1366×768 usability.

---

# 12. Acceptance criteria

The task is complete when:

- Reference and Target controls are compact.
- Browse and Configure sit directly beside each file.
- Format status no longer consumes a large independent row.
- Main actions form a clean right-side column.
- Shot Interval is removed from the main interface.
- Existing Shot Interval/QC-distance behaviour remains available through Settings.
- Primary QC summary is significantly simpler.
- Detailed QC categories remain accessible.
- Visible QC descriptions are human-readable.
- QC table columns can be reordered by drag-and-drop.
- New column order persists after restarting the app.
- Reset Columns restores default order.
- Existing column visibility controls still work.
- TASK-UI-001 responsive/overlay behaviour remains intact.
- Typecheck passes.
- Desktop tests pass.
- Desktop build passes.
- Visual verification is performed at 1440×900 and 1366×768.
- No matching, engine, correction or QC detection files are modified.

After acceptance, stop UI feature development and return the result for CTO manual review.