<!-- CTO task text, copied verbatim from Mert's project message of 2026-10-02 12:09 UTC. -->

TASK-UI-PERF — QC Table Performance
Profile the real OS_A-2 dataset (~6.7k rows) and remove UI jank without changing any product logic.
Primary targets:

* virtualize/window QC table rows so only visible rows plus a small overscan are mounted;
* preserve sticky headers, horizontal scrolling, row selection, QC navigation and column ordering;
* optimize column drag so pointer movement does not rerender the full table;
* cache header geometry at drag start rather than reading layout on every pointer event;
* throttle visual drag updates with `requestAnimationFrame` where appropriate;
* avoid repeated expensive QC description computation during render;
* keep localStorage column persistence unchanged.

Do not touch engine, matching, correction or QC detection.
Test with a dataset equivalent to OS_A-2 size, not only synthetic small tables.
Measure before/after:

* mounted table row count,
* drag responsiveness,
* scroll responsiveness,
* analysis-result render time.

Run desktop tests, typecheck and build.
Do not add animation or React Bits in this task.
