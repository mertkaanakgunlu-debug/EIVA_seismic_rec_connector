import type { AnalysisSummary, EngineRecord, FfidJump } from "./types";
import { formatAssociation, formatQc } from "./presentation";

export function nextCycle(indices: number[], current: number | null, step: 1 | -1): number | null {
  if (!indices.length) return null;
  if (current === null || !indices.includes(current)) return step === 1 ? indices[0] : indices[indices.length - 1];
  return indices[(indices.indexOf(current) + step + indices.length) % indices.length];
}

export type GroupKey = "TARGET_ONLY" | "NEEDS_REVIEW" | "INVALID" | "BLOCKED" | "QC_SEVERE" | "QC_WARNING" | "POSITION_JUMP";
export const GROUP_KEYS: GroupKey[] = ["TARGET_ONLY", "NEEDS_REVIEW", "INVALID", "BLOCKED", "QC_SEVERE", "QC_WARNING", "POSITION_JUMP"];

/**
 * Row indices behind each navigable counter. Association statuses and QC severities are independent axes.
 * NEEDS_REVIEW is a presentation aggregate of the existing categories: unmatched recorder records plus every
 * non-EIVA-only row with a warning or severe QC finding (EIVA-only rows have their own counter).
 */
export function groupIndices(records: EngineRecord[]): Record<GroupKey, number[]> {
  const groups: Record<GroupKey, number[]> = { TARGET_ONLY: [], NEEDS_REVIEW: [], INVALID: [], BLOCKED: [], QC_SEVERE: [], QC_WARNING: [], POSITION_JUMP: [] };
  records.forEach((record, index) => {
    if (record.association === "BLOCKED" || (record.association !== "TARGET_ONLY" && (record.qc_severity === "SEVERE" || record.qc_severity === "WARNING"))) groups.NEEDS_REVIEW.push(index);
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

/**
 * Full column order: the saved order first (unknown keys dropped), then any column the saved order does not
 * know, inserted after its predecessor in the default order so new columns keep a sensible place.
 */
export function mergeColumnOrder(saved: readonly string[] | null | undefined, defaults: readonly string[]): string[] {
  const known = new Set(defaults);
  const order = (saved || []).filter((key, index, all) => known.has(key) && all.indexOf(key) === index);
  defaults.forEach((key, index) => {
    if (order.includes(key)) return;
    const previous = index > 0 ? order.indexOf(defaults[index - 1]) : -1;
    order.splice(previous + 1, 0, key);
  });
  return order;
}

/** The visible columns in display order. */
export function orderedVisibleColumns(order: readonly string[], visible: readonly string[]): string[] {
  const shown = new Set(visible);
  return [...order.filter((key) => shown.has(key)), ...visible.filter((key) => !order.includes(key))];
}

/**
 * Move a visible column so it lands at `dropIndex` among the visible columns (0 = first, length = last),
 * keeping hidden columns where they were.
 */
export function moveColumn(order: readonly string[], visible: readonly string[], key: string, dropIndex: number): string[] {
  const shown = orderedVisibleColumns(order, visible);
  const from = shown.indexOf(key);
  if (from < 0) return [...order];
  const rest = shown.filter((column) => column !== key);
  const at = Math.max(0, Math.min(rest.length, dropIndex > from ? dropIndex - 1 : dropIndex));
  const full = [...order, ...shown.filter((column) => !order.includes(column))].filter((column) => column !== key);
  const before = rest[at];
  full.splice(before === undefined ? full.indexOf(rest[rest.length - 1]) + 1 : full.indexOf(before), 0, key);
  return full;
}

export const COLUMN_ORDER_STORAGE_KEY = "shotlogfixer-qc-column-order";

export function loadColumnOrder(storage: Pick<Storage, "getItem"> | undefined): string[] | null {
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(COLUMN_ORDER_STORAGE_KEY) || "null");
    return Array.isArray(parsed) && parsed.every((key) => typeof key === "string") ? parsed : null;
  } catch { return null; }
}

export function saveColumnOrder(storage: Pick<Storage, "setItem" | "removeItem"> | undefined, order: readonly string[] | null) {
  try {
    if (order) storage?.setItem(COLUMN_ORDER_STORAGE_KEY, JSON.stringify(order));
    else storage?.removeItem(COLUMN_ORDER_STORAGE_KEY);
  } catch { /* Storage can be unavailable; the order then lasts for this session only. */ }
}

/**
 * Rows of a windowed table to mount for a scroll position: the rows intersecting the viewport plus `overscan`
 * rows on each side. `offset` is the scroll distance from the first body row; `end` is exclusive.
 */
export function tableRowWindow(offset: number, viewportHeight: number, rowHeight: number, total: number, overscan: number): { start: number; end: number } {
  if (total <= 0 || rowHeight <= 0) return { start: 0, end: 0 };
  const first = Math.floor(Math.max(0, offset) / rowHeight);
  const last = Math.ceil((Math.max(0, offset) + Math.max(0, viewportHeight)) / rowHeight);
  return { start: Math.max(0, Math.min(total - 1, first) - overscan), end: Math.min(total, Math.max(first + 1, last) + overscan) };
}

/** Drop position among headers whose horizontal midpoints are `midpoints`: the first header the pointer is left of. */
export function columnDropIndex(x: number, midpoints: readonly number[]): number {
  const index = midpoints.findIndex((mid) => x < mid);
  return index < 0 ? midpoints.length : index;
}
