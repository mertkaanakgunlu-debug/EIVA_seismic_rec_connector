import { describe, expect, it } from "vitest";
import { COLUMN_ORDER_STORAGE_KEY, columnAlignment, columnDropIndex, ffidJumpTargets, getCellValue, groupIndices, loadColumnOrder, mergeColumnOrder, moveColumn, nextCycle, orderedVisibleColumns, PLACEHOLDER, saveColumnOrder, recordTone, resolveThemePreference, summaryForDisplay, tableRowWindow, timelineLogicalX, timelinePositionForRecord, timelineRecordIndexAtX } from "./logic";
import { describeFinding, describeRecord, formatAssociation, formatQc, formatQcCode, formatSeverity } from "./presentation";
import type { EngineRecord } from "./types";

const row = (overrides: Partial<EngineRecord>): EngineRecord => ({
  id: "row-1", acquisition_position: 1, association: "ASSIGNED", reference_ffid: "6873", reference_line: 6764, reference_x: 633293.29, reference_y: 4657173.31,
  target_ffid: "6873", target_line: 6770, target_x: 633110.55, target_y: 4657069.19, corrected_ffid: "6873", distance_m: 210.32, basis: "SEQUENCE", confidence: "LOW",
  qc_severity: "SEVERE", qc_codes: ["RECORDER_POSITION_JUMP", "ASSOCIATION_DISTANCE_SEVERE", "ASSOCIATION_SEQUENCE_ONLY"], diagnostic: "", target_values: { NOTE: "x" }, ...overrides,
});

describe("navigation helpers", () => {
  it("wraps problem navigation in both directions", () => {
    expect(nextCycle([2, 7], null, 1)).toBe(2);
    expect(nextCycle([2, 7], 7, 1)).toBe(2);
    expect(nextCycle([2, 7], 2, -1)).toBe(7);
  });

  it("resolves and persists theme intent", () => {
    expect(resolveThemePreference("dark", false)).toBe("dark");
    expect(resolveThemePreference("system", true)).toBe("dark");
    expect(resolveThemePreference(null, false)).toBe("light");
  });

  it("maps records by acquisition position", () => {
    expect(timelinePositionForRecord({ acquisition_position: 183 } as never)).toBe(183);
    expect(timelinePositionForRecord(undefined)).toBe(1);
  });

  it("maps timeline hit testing by acquisition position", () => {
    const records = [{ acquisition_position: 1 }, { acquisition_position: 50 }, { acquisition_position: 100 }] as never[];
    expect(timelineRecordIndexAtX(records, 0, 1000, 100)).toBe(0);
    expect(timelineRecordIndexAtX(records, 990, 1000, 100)).toBe(2);
  });

  it("uses one logical coordinate after horizontal scrolling", () => {
    expect(timelineLogicalX(140, 100, 300)).toBe(340);
  });
});

describe("association and QC are separate axes", () => {
  it("shows an assigned record with a severe QC finding as matched, not unmatched", () => {
    const record = row({});
    expect(getCellValue(record, "association")).toBe("Matched");
    expect(getCellValue(record, "qc")).toBe("Recorder position jump +2");
    expect(getCellValue(record, "corrected_ffid")).toBe("6873");
    expect(getCellValue(record, "distance")).toBe("210.320");
    expect(recordTone(record)).toBe("severe");
    expect(recordTone(row({ qc_severity: "INFO", qc_codes: ["ASSOCIATION_DISTANCE_ELEVATED"] }))).toBe("ok");
    expect(recordTone(row({ qc_severity: "WARNING" }))).toBe("warning");
  });

  it("renders a clear placeholder when a side has no value", () => {
    const targetOnly = row({ association: "TARGET_ONLY", reference_ffid: null, reference_x: null, reference_y: null, corrected_ffid: null, distance_m: null, basis: null, confidence: null, qc_severity: "INFO", qc_codes: ["TARGET_ONLY"] });
    for (const key of ["reference_ffid", "reference_coord", "corrected_ffid", "distance", "basis", "confidence"]) expect(getCellValue(targetOnly, key)).toBe(PLACEHOLDER);
    expect(getCellValue(targetOnly, "association")).toBe("EIVA-only");
    expect(recordTone(targetOnly)).toBe("target-only");
    expect(getCellValue(row({}), "target_raw:NOTE")).toBe("x");
    expect(getCellValue(row({}), "target_raw:MISSING")).toBe(PLACEHOLDER);
  });

  it("groups rows for navigation by association and by severity independently", () => {
    const records = [
      row({ id: "a", qc_severity: "OK", qc_codes: [] }),
      row({ id: "b", association: "TARGET_ONLY", qc_severity: "INFO", qc_codes: ["TARGET_ONLY"] }),
      row({ id: "c", qc_severity: "WARNING", qc_codes: ["ASSOCIATION_DISTANCE_LARGE"] }),
      row({ id: "d", association: "INVALID", qc_severity: "WARNING", qc_codes: ["RECORDER_INVALID_ROW"] }),
      row({ id: "e" }),
    ];
    const groups = groupIndices(records);
    expect(groups.TARGET_ONLY).toEqual([1]);
    expect(groups.INVALID).toEqual([3]);
    expect(groups.QC_WARNING).toEqual([2, 3]);
    expect(groups.QC_SEVERE).toEqual([4]);
    expect(groups.POSITION_JUMP).toEqual([4]);
  });

  it("aggregates review rows without counting EIVA-only rows twice", () => {
    const records = [
      row({ id: "a", qc_severity: "OK", qc_codes: [] }),
      row({ id: "b", association: "TARGET_ONLY", qc_severity: "WARNING", qc_codes: ["TARGET_ONLY_BLOCK", "TARGET_ONLY"] }),
      row({ id: "c", qc_severity: "WARNING", qc_codes: ["ASSOCIATION_DISTANCE_LARGE"] }),
      row({ id: "d", association: "BLOCKED", qc_severity: "SEVERE", qc_codes: ["ASSOCIATION_BLOCKED"] }),
      row({ id: "e", qc_severity: "INFO", qc_codes: ["ASSOCIATION_DISTANCE_ELEVATED"] }),
      row({ id: "f", association: "INVALID", qc_severity: "WARNING", qc_codes: ["RECORDER_INVALID_ROW"] }),
    ];
    const groups = groupIndices(records);
    expect(groups.NEEDS_REVIEW).toEqual([2, 3, 5]);
    expect(groups.TARGET_ONLY).toEqual([1]);
    expect(groups.BLOCKED).toEqual([3]);
  });

  it("resolves FFID jump targets from the recorder discontinuities", () => {
    const records = [row({ id: "row-1" }), row({ id: "row-2" })];
    expect(ffidJumpTargets(records, [{ from: 543, to: 553, kind: "GAP", row_id: "row-2" }, { from: 1, to: 9, kind: "GAP", row_id: null }])).toEqual([1, null]);
    expect(columnAlignment("distance")).toBe("center");
    expect(columnAlignment("diagnostic")).toBe("left");
  });

  it("summarises correction counts without implying QC warnings are unmatched shots", () => {
    const summary = summaryForDisplay({ reference_rows: 6764, reference_valid: 6764, reference_no_shot: 0, reference_invalid: 0, target_rows: 6769, target_invalid: 0, assigned: 6762, target_only: 7, invalid_target_removed: 0, blocked: 2, corrected_rows: 6762, expected_rows: 6764, qc_info: 298, qc_warning: 12, qc_severe: 3, assigned_with_warning: 12, assigned_with_severe: 0 });
    expect(summary).toMatchObject({ assigned: 6762, targetOnly: 7, blocked: 2, correctedRows: 6762, expectedRows: 6764, qcSevere: 3, qcWarning: 12 });
  });

  it("keeps canonical codes while presenting readable labels", () => {
    expect(formatAssociation("ASSIGNED")).toBe("Matched");
    expect(formatAssociation("TARGET_ONLY")).toBe("EIVA-only");
    expect(formatAssociation("BLOCKED")).toBe("Unmatched");
    expect(formatSeverity("OK")).toBe("OK");
    expect(formatQcCode("ASSOCIATION_DISTANCE_LARGE")).toBe("Far from EIVA position");
    expect(formatQcCode("ASSOCIATION_BLOCKED")).toBe("No EIVA match");
    expect(formatQcCode("SOMETHING_NEW")).toBe("something new");
    expect(formatQc({ qc_severity: "OK", qc_codes: [] })).toBe("OK");
  });
});

describe("human-readable QC notes", () => {
  it("describes EIVA-only rows and their consequence", () => {
    const note = describeFinding({ code: "TARGET_ONLY", message: "Target row at line 9 ...", metrics: { previous_reference_ffid: "244", next_reference_ffid: "245", no_shot_rows: 0 } });
    expect(note.text).toBe("EIVA position has no recorder counterpart. This row will not be included in the corrected EIVA file.");
    expect(note.detail).toBe("It lies between recorder FFID 244 and 245.");
  });

  it("describes an unmatched recorder record by what the operator can observe", () => {
    const note = describeFinding({ code: "ASSOCIATION_BLOCKED", message: "... (it fits it better, 1.20 m) ...", metrics: { nearest_distance_m: 210.4, nearest_target_row: 12, shift_records: null, shift_cost_m: null } }, row({ reference_ffid: "6873" }));
    expect(note.text).toBe("Recorder FFID 6873 could not be matched to a nearby EIVA position.");
    expect(note.detail).toContain("Its nearest EIVA position (about 210 m away) is already matched to another recorder shot or is out of shot order");
    expect(`${note.text} ${note.detail}`).not.toMatch(/fits it better/);
  });

  it("describes recorder FFID jumps as a sequence change", () => {
    expect(describeFinding({ code: "RECORDER_FFID_DISCONTINUITY", message: "FFID jumps from 245 to 247 (1 missing).", metrics: { from: 245, to: 247, kind: "GAP" } }).text).toBe("Recorder FFID sequence jumps from 245 to 247.");
    expect(describeFinding({ code: "RECORDER_FFID_DISCONTINUITY", message: "", metrics: { from: 250, to: 248, kind: "REVERSAL" } }).text).toBe("Recorder FFID sequence goes back from 250 to 248.");
  });

  it("falls back to the engine message in operator vocabulary for unknown codes", () => {
    expect(describeFinding({ code: "SOMETHING_NEW", message: "Target row at line 4 has no target value.", metrics: {} }).text).toBe("EIVA row at line 4 has no EIVA value.");
  });

  it("uses the row's most severe finding, or its association when it has none", () => {
    const blocked = row({ association: "BLOCKED", reference_ffid: "12", qc_codes: [] });
    expect(describeRecord(blocked, [])?.text).toBe("Recorder FFID 12 could not be matched to a nearby EIVA position.");
    expect(describeRecord(row({ qc_severity: "OK", qc_codes: [] }), [])).toBeNull();
  });
});

describe("QC column order", () => {
  const defaults = ["a", "b", "c", "d"];

  it("restores a saved order and keeps new columns near their default neighbour", () => {
    expect(mergeColumnOrder(null, defaults)).toEqual(defaults);
    expect(mergeColumnOrder(["c", "a", "b", "d"], defaults)).toEqual(["c", "a", "b", "d"]);
    expect(mergeColumnOrder(["d", "a", "gone"], defaults)).toEqual(["d", "a", "b", "c"]);
    expect(mergeColumnOrder(["b", "b", "a"], ["a", "b"])).toEqual(["b", "a"]);
  });

  it("moves a visible column to the drop position and leaves hidden columns in place", () => {
    expect(moveColumn(defaults, defaults, "a", 4)).toEqual(["b", "c", "d", "a"]);
    expect(moveColumn(defaults, defaults, "d", 0)).toEqual(["d", "a", "b", "c"]);
    expect(moveColumn(defaults, defaults, "b", 1)).toEqual(defaults);
    expect(moveColumn(defaults, defaults, "b", 2)).toEqual(defaults);
    expect(moveColumn(defaults, ["a", "c", "d"], "d", 1)).toEqual(["a", "b", "d", "c"]);
    expect(orderedVisibleColumns(["c", "a", "b"], ["a", "c"])).toEqual(["c", "a"]);
  });

  it("persists the order locally and tolerates missing or corrupt storage", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => { store.set(key, value); }, removeItem: (key: string) => { store.delete(key); } };
    saveColumnOrder(storage, ["b", "a"]);
    expect(loadColumnOrder(storage)).toEqual(["b", "a"]);
    saveColumnOrder(storage, null);
    expect(loadColumnOrder(storage)).toBeNull();
    store.set(COLUMN_ORDER_STORAGE_KEY, "{not json");
    expect(loadColumnOrder(storage)).toBeNull();
    expect(loadColumnOrder(undefined)).toBeNull();
    expect(() => saveColumnOrder({ setItem: () => { throw new Error("full"); }, removeItem: () => undefined }, ["a"])).not.toThrow();
  });
});

describe("QC table windowing", () => {
  it("mounts the visible rows plus overscan, clamped to the table", () => {
    expect(tableRowWindow(0, 300, 30, 6772, 8)).toEqual({ start: 0, end: 18 });
    expect(tableRowWindow(3000, 300, 30, 6772, 8)).toEqual({ start: 92, end: 118 });
    expect(tableRowWindow(6772 * 30, 300, 30, 6772, 8)).toEqual({ start: 6763, end: 6772 });
    expect(tableRowWindow(-40, 300, 30, 5, 8)).toEqual({ start: 0, end: 5 });
    expect(tableRowWindow(0, 300, 30, 0, 8)).toEqual({ start: 0, end: 0 });
  });

  it("drops a dragged column before the first header whose midpoint lies right of the pointer", () => {
    const mids = [50, 150, 260];
    expect(columnDropIndex(10, mids)).toBe(0);
    expect(columnDropIndex(149, mids)).toBe(1);
    expect(columnDropIndex(150, mids)).toBe(2);
    expect(columnDropIndex(400, mids)).toBe(3);
  });
});
