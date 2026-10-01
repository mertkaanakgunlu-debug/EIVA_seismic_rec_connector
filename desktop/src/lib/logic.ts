import type { AnalysisSummary, EngineRecord, Status } from "./types";

export function nextCycle(indices: number[], current: number | null, step: 1 | -1): number | null {
  if (!indices.length) return null;
  if (current === null || !indices.includes(current)) return step === 1 ? indices[0] : indices[indices.length - 1];
  return indices[(indices.indexOf(current) + step + indices.length) % indices.length];
}

export function statusIndices(records: EngineRecord[], status: Status): number[] {
  return records.reduce<number[]>((indices, record, index) => {
    if (record.status === status) indices.push(index);
    return indices;
  }, []);
}

export function resolveThemePreference(preference: string | null, systemDark: boolean): "light" | "dark" {
  if (preference === "light" || preference === "dark") return preference;
  return systemDark ? "dark" : "light";
}

export function timelinePositionForRecord(record: EngineRecord | undefined): number {
  return Math.max(1, record?.acquisition_position ?? 1);
}

export function formatCoordinate(x: number | null, y: number | null): string {
  return x === null || y === null ? "" : `${x.toFixed(2)}, ${y.toFixed(2)}`;
}

export function basename(filePath: string): string {
  return filePath.split(/[\\/]/).pop() || filePath;
}

export function summaryForDisplay(summary: AnalysisSummary) {
  return {
    matched: summary.matched,
    eivaOnly: summary.eiva_only,
    invalid: summary.recorder_invalid,
    review: summary.review,
    totalIssues: summary.total_issues,
  };
}
