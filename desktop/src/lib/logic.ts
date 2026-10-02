import type { AnalysisSummary, EngineRecord, FfidJump } from "./types";
import { formatAssociation, formatQc } from "./presentation";

export function nextCycle(indices: number[], current: number | null, step: 1 | -1): number | null {
  if (!indices.length) return null;
  if (current === null || !indices.includes(current)) return step === 1 ? indices[0] : indices[indices.length - 1];
  return indices[(indices.indexOf(current) + step + indices.length) % indices.length];
}

export type GroupKey = "TARGET_ONLY" | "INVALID" | "BLOCKED" | "QC_SEVERE" | "QC_WARNING" | "POSITION_JUMP";
export const GROUP_KEYS: GroupKey[] = ["TARGET_ONLY", "INVALID", "BLOCKED", "QC_SEVERE", "QC_WARNING", "POSITION_JUMP"];

/** Row indices behind each navigable counter. Association statuses and QC severities are independent axes. */
export function groupIndices(records: EngineRecord[]): Record<GroupKey, number[]> {
  const groups: Record<GroupKey, number[]> = { TARGET_ONLY: [], INVALID: [], BLOCKED: [], QC_SEVERE: [], QC_WARNING: [], POSITION_JUMP: [] };
  records.forEach((record, index) => {
    if (record.association === "TARGET_ONLY") groups.TARGET_ONLY.push(index);
    else if (record.association === "INVALID" || record.association === "NO_SHOT") groups.INVALID.push(index);
    else if (record.association === "BLOCKED") groups.BLOCKED.push(index);
    if (record.qc_severity === "SEVERE") groups.QC_SEVERE.push(index);
    else if (record.qc_severity === "WARNING") groups.QC_WARNING.push(index);
    if (record.qc_codes.some((code) => code === "RECORDER_POSITION_JUMP" || code === "RECORDER_POSITION_SPIKE")) groups.POSITION_JUMP.push(index);
  });
  return groups;
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

/** Recorder FFID discontinuities, resolved to the result row that follows the jump. */
export function ffidJumpTargets(records: EngineRecord[], jumps: FfidJump[]): Array<number | null> {
  return jumps.map((jump) => {
    const index = jump.row_id ? records.findIndex((record) => record.id === jump.row_id) : -1;
    return index >= 0 ? index : null;
  });
}

/** Rendered when one side of a row has no value (never an empty-looking cell). */
export const PLACEHOLDER = "—";

export function getCellValue(record: EngineRecord, key: string): string {
  switch (key) {
    case "reference_ffid": return record.reference_ffid || PLACEHOLDER;
    case "target_ffid": return record.target_ffid || PLACEHOLDER;
    case "corrected_ffid": return record.corrected_ffid || PLACEHOLDER;
    case "reference_coord": return formatCoordinate(record.reference_x, record.reference_y) || PLACEHOLDER;
    case "target_coord": return formatCoordinate(record.target_x, record.target_y) || PLACEHOLDER;
    case "distance": return record.distance_m === null ? PLACEHOLDER : record.distance_m.toFixed(3);
    case "association": return formatAssociation(record.association);
    case "qc": return formatQc(record);
    case "basis": return record.basis === "SPATIAL" ? "Spatial" : record.basis === "SEQUENCE" ? "Sequence" : PLACEHOLDER;
    case "confidence": return record.confidence ? record.confidence.charAt(0) + record.confidence.slice(1).toLowerCase() : PLACEHOLDER;
    case "reference_line": return record.reference_line === null ? PLACEHOLDER : String(record.reference_line);
    case "target_line": return record.target_line === null ? PLACEHOLDER : String(record.target_line);
    case "diagnostic": return record.diagnostic || PLACEHOLDER;
    default: return key.startsWith("target_raw:") ? (record.target_values[key.slice("target_raw:".length)] ?? PLACEHOLDER) : "";
  }
}

export function columnAlignment(key: string): "center" | "left" {
  return ["reference_ffid", "target_ffid", "corrected_ffid", "reference_coord", "target_coord", "distance", "association", "qc"].includes(key) ? "center" : "left";
}

/** Colour family of a result row on the timeline and in the table: association first, QC severity second. */
export function recordTone(record: EngineRecord): "ok" | "warning" | "severe" | "target-only" | "invalid" {
  if (record.association === "TARGET_ONLY") return "target-only";
  if (record.association !== "ASSIGNED") return "invalid";
  if (record.qc_severity === "SEVERE") return "severe";
  return record.qc_severity === "WARNING" ? "warning" : "ok";
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
    assigned: summary.assigned,
    targetOnly: summary.target_only,
    invalid: summary.reference_invalid + summary.target_invalid,
    blocked: summary.blocked,
    correctedRows: summary.corrected_rows,
    expectedRows: summary.expected_rows,
    qcSevere: summary.qc_severe,
    qcWarning: summary.qc_warning,
  };
}
