import { describe, expect, it } from "vitest";
import { columnAlignment, ffidJumpTargets, getCellValue, nextCycle, resolveThemePreference, summaryForDisplay, timelineLogicalX, timelinePositionForRecord, timelineRecordIndexAtX } from "./logic";

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

  it("resolves status display and FFID jump targets", () => {
    const records = [{ eiva_ffid: "543", status: "EIVA_ONLY", eiva_values: {} }, { eiva_ffid: "553", status: "MATCHED", eiva_values: {} }] as never[];
    expect(getCellValue(records[0], "status")).toBe("EIVA_ONLY");
    expect(ffidJumpTargets(records, [{ from: "543", to: "553" }])).toEqual([1]);
    expect(columnAlignment("distance")).toBe("center");
    expect(columnAlignment("diagnostic")).toBe("left");
  });

  it("keeps total issues as issue-region count", () => {
    expect(summaryForDisplay({ eiva_rows: 2816, recorder_rows: 2814, matched: 2813, eiva_only: 2, recorder_invalid: 1, review: 1, total_issues: 2 }).totalIssues).toBe(2);
  });
});
