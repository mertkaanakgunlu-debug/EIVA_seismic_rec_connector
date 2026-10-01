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

export function timelineMarkerX(record: EngineRecord, trackWidth: number, total: number): number {
  return 4 + ((timelinePositionForRecord(record) - 1) / Math.max(1, total - 1)) * Math.max(0, trackWidth - 8);
}

export function timelineRecordIndexAtX(records: EngineRecord[], x: number, trackWidth: number, total: number, hitRadius = 9): number | null {
  if (!records.length || trackWidth <= 0 || total <= 0) return null;
  let bestIndex: number | null = null;
  let bestDistance = hitRadius;
  records.forEach((record, index) => {
    const distance = Math.abs(timelineMarkerX(record, trackWidth, total) - x);
    if (distance <= bestDistance && (bestIndex === null || distance < bestDistance)) { bestDistance = distance; bestIndex = index; }
  });
  return bestIndex;
}

export function ffidJumpTargets(records: EngineRecord[], jumps: Array<{ from: string; to: string }>): Array<number | null> {
  return jumps.map((jump) => {
    // These discontinuities come from original EIVA acquisition order, not recorder FFIDs.
    const to = records.findIndex((record) => record.eiva_ffid === jump.to);
    if (to >= 0) return to;
    const from = records.findIndex((record) => record.eiva_ffid === jump.from);
    if (from >= 0 && from + 1 < records.length) return from + 1;
    return null;
  });
}

export function getCellValue(record: EngineRecord, key: string): string {
  switch (key) {
    case "eiva_ffid": return record.eiva_ffid || "";
    case "recorder_ffid": return record.recorder_ffid || "";
    case "eiva_coord": return formatCoordinate(record.eiva_easting, record.eiva_northing);
    case "recorder_coord": return record.status === "NO_SHOT" ? "No shot recorded" : formatCoordinate(record.recorder_x, record.recorder_y);
    case "distance": return record.distance_m === null ? "" : record.distance_m.toFixed(3);
    case "status": return record.status;
    case "recorder_x": return record.recorder_x === null ? "" : record.recorder_x.toFixed(2);
    case "recorder_y": return record.recorder_y === null ? "" : record.recorder_y.toFixed(2);
    case "diagnostic": return record.diagnostic;
    default: return key.startsWith("eiva_raw:") ? record.eiva_values[key.slice("eiva_raw:".length)] || "" : "";
  }
}

export function columnAlignment(key: string): "center" | "left" {
  return ["eiva_ffid", "recorder_ffid", "eiva_coord", "recorder_coord", "distance", "status"].includes(key) ? "center" : "left";
}

/** Convert a pointer position in the scrolling viewport to the canvas' logical coordinate. */
export function timelineLogicalX(clientX: number, viewportLeft: number, scrollLeft: number): number {
  return clientX - viewportLeft + scrollLeft;
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
