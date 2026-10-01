import { describe, expect, it } from "vitest";
import { nextCycle, resolveThemePreference, summaryForDisplay, timelinePositionForRecord } from "./logic";

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

  it("keeps total issues as issue-region count", () => {
    expect(summaryForDisplay({ eiva_rows: 2816, recorder_rows: 2814, matched: 2813, eiva_only: 2, recorder_invalid: 1, review: 1, total_issues: 2 }).totalIssues).toBe(2);
  });
});
