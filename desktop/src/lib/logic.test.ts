import { describe, expect, it } from "vitest";
import { columnAlignment, ffidJumpTargets, getCellValue, groupIndices, nextCycle, PLACEHOLDER, recordTone, resolveThemePreference, summaryForDisplay, timelineLogicalX, timelinePositionForRecord, timelineRecordIndexAtX } from "./logic";
import { formatAssociation, formatQc, formatQcCode, formatSeverity } from "./presentation";
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
  it("shows an assigned record with a severe QC finding as assigned, not unmatched", () => {
    const record = row({});
    expect(getCellValue(record, "association")).toBe("Assigned");
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
    expect(getCellValue(targetOnly, "association")).toBe("Target-only");
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
    expect(formatAssociation("TARGET_ONLY")).toBe("Target-only");
    expect(formatAssociation("BLOCKED")).toBe("Blocked");
    expect(formatSeverity("OK")).toBe("OK");
    expect(formatQcCode("ASSOCIATION_DISTANCE_LARGE")).toBe("High distance");
    expect(formatQcCode("ASSOCIATION_BLOCKED")).toBe("No target row");
    expect(formatQcCode("SOMETHING_NEW")).toBe("something new");
    expect(formatQc({ qc_severity: "OK", qc_codes: [] })).toBe("OK");
  });
});
