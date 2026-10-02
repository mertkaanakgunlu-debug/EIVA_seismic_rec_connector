<!-- CTO task text, copied verbatim from Mert's project message of 2026-10-02 11:26 UTC. -->

TASK-UI-001 — Window and Overlay Polish
Objective
Make the desktop application visually complete and usable immediately after launch.
Do not modify matching, QC logic, correction logic, or file processing.
Scope
1. Default application window
The application must open at a size that shows the complete primary interface without requiring the user to manually maximize or resize it.

* Choose a sensible larger default desktop size.
* Respect the available screen/work area.
* Keep reasonable minimum width and height.
* The layout must remain usable on smaller laptop screens.
* Do not solve this only by hard-coding an unnecessarily huge window.

The version/footer area must be visible or naturally reachable in the normal layout.
Avoid content being silently clipped below the viewport.
2. Main layout
Review the vertical and horizontal layout.

* Primary controls must remain visible.
* Long content areas may scroll internally where appropriate.
* Avoid unnecessary full-page overflow.
* Panels should not overlap one another.
* Bottom status/version content should remain properly positioned.

3. Popovers, menus and selectors
Fix all floating UI elements, including the theme selector and similar menus.
They must:

* appear above surrounding cards, tables and panels;
* not be clipped by parent containers;
* remain fully visible near viewport edges;
* use consistent stacking behaviour;
* close naturally when clicking outside.

Prefer a proper portal/popover layer rather than solving individual cases with arbitrary large `z-index` values.
4. Visual consistency
Review:

* border radius,
* spacing,
* card widths,
* dropdown widths,
* panel alignment,
* popup alignment.

Use one consistent visual system.
Do not redesign the product.
Acceptance criteria

* App launches at a useful default size.
* Main interface is usable without immediately resizing the window.
* Version/footer is visible or naturally reachable.
* Theme selector and every other floating panel render above surrounding components.
* No dropdown/popover is clipped.
* No regression in small-window resizing.
* Existing desktop tests and typecheck pass.
* Matching/correction source files are untouched.
