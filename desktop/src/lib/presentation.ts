import type { Association, EngineRecord, QcFinding, QcSeverity } from "./types";

const ASSOCIATION_LABELS: Record<Association, string> = {
  ASSIGNED: "Matched", TARGET_ONLY: "EIVA-only", INVALID: "Invalid", NO_SHOT: "No shot", BLOCKED: "Unmatched recorder",
};
const SEVERITY_LABELS: Record<QcSeverity, string> = { OK: "OK", INFO: "Note", WARNING: "Warning", SEVERE: "Severe" };
// Short operator-facing labels for the QC table cell. The canonical codes stay in the data and in the QC export.
const QC_LABELS: Record<string, string> = {
  RECORDER_INVALID_ROW: "Recorder row unreadable",
  RECORDER_NO_SHOT_ROW: "Recorder no-shot row",
  RECORDER_DUPLICATE_FFID: "Duplicate recorder FFID",
  RECORDER_FFID_DISCONTINUITY: "Recorder FFID jump",
  RECORDER_DUPLICATE_COORDINATE: "Recorder repeated position",
  RECORDER_POSITION_JUMP: "Recorder position jump",
  RECORDER_POSITION_SPIKE: "Recorder position spike",
  RECORDER_SPACING_IRREGULAR: "Recorder spacing irregular",
  SHOT_INTERVAL_MISMATCH: "Shot interval mismatch",
  TARGET_INVALID_ROW: "EIVA row unreadable",
  TARGET_ONLY: "No recorder shot",
  TARGET_ONLY_BLOCK: "Several EIVA-only rows",
  TARGET_POSITION_JUMP: "EIVA position jump",
  TARGET_POSITION_SPIKE: "EIVA position spike",
  TARGET_DUPLICATE_COORDINATE: "EIVA repeated position",
  TARGET_SPACING_IRREGULAR: "EIVA spacing irregular",
  TARGET_DUPLICATE_FFID: "Duplicate EIVA FFID",
  TARGET_FFID_DISCONTINUITY: "EIVA FFID jump",
  ASSOCIATION_DISTANCE_ELEVATED: "Slightly far",
  ASSOCIATION_DISTANCE_LARGE: "Far from EIVA position",
  ASSOCIATION_DISTANCE_SEVERE: "Very far from EIVA position",
  ASSOCIATION_SEQUENCE_ONLY: "Matched by shot order",
  ASSOCIATION_AMBIGUOUS: "Ambiguous match",
  ASSOCIATION_NEAREST_OVERRIDDEN: "Closer position unused",
  ASSOCIATION_RUN_DISPLACED: "Possible one-shot offset",
  ASSOCIATION_BLOCKED: "No EIVA match",
};

const BLOCKER_LABELS: Record<string, string> = {
  REFERENCE_ROWS_INVALID: "Recorder rows cannot be interpreted",
  NO_REFERENCE_RECORDS: "No valid recorder records",
  NO_TARGET_ROWS: "No EIVA rows",
  INSUFFICIENT_TARGET_ROWS: "Too few EIVA rows for a one-to-one match",
  TARGET_FFID_FIELD_MISSING: "EIVA FFID field missing",
  CORRECTED_COPY_FAILED_VALIDATION: "Corrected copy failed validation",
};

export const formatBlocker = (code: string): string => BLOCKER_LABELS[code] ?? code.toLowerCase().replace(/_/g, " ");
export const formatAssociation = (association: Association): string => ASSOCIATION_LABELS[association] ?? association;
export const formatSeverity = (severity: QcSeverity): string => SEVERITY_LABELS[severity] ?? severity;
export const formatQcCode = (code: string): string => QC_LABELS[code] ?? code.toLowerCase().replace(/_/g, " ");

/** The QC cell: the most severe observation of the row (the engine lists codes most severe first). */
export function formatQc(record: Pick<EngineRecord, "qc_severity" | "qc_codes">): string {
  if (record.qc_severity === "OK" || !record.qc_codes.length) return "OK";
  const extra = record.qc_codes.length - 1;
  return `${formatQcCode(record.qc_codes[0])}${extra > 0 ? ` +${extra}` : ""}`;
}

const metres = (value: unknown, digits = 2): string | null => typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(digits)} m` : null;
const roughMetres = (value: number): string => `${value >= 10 ? Math.round(value).toLocaleString() : value.toFixed(1)} m`;
const count = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const plural = (n: number, word: string, many = `${word}s`) => `${n.toLocaleString()} ${n === 1 ? word : many}`;

/** Fallback for codes without a dedicated sentence: the engine message in operator vocabulary. */
const operatorWording = (message: string): string => message
  .replace(/\btarget rows\b/g, "EIVA rows").replace(/\btarget row\b/g, "EIVA row")
  .replace(/\bTarget row\b/g, "EIVA row").replace(/\bTarget\b/g, "EIVA").replace(/\btarget\b/g, "EIVA");

export interface QcDescription {
  /** What the operator sees, in plain words. */
  text: string;
  /** Optional consequence or context sentence. */
  detail?: string;
}

type DescribedRecord = Pick<EngineRecord, "reference_ffid" | "target_ffid" | "distance_m">;

/**
 * Plain-language description of one QC finding. Presentation only: the finding, its severity and its
 * code are unchanged, and the engine message remains available as technical detail.
 */
export function describeFinding(finding: Pick<QcFinding, "code" | "message" | "metrics">, record?: DescribedRecord | null, shotInterval?: number): QcDescription {
  const m = finding.metrics || {};
  const recorder = record?.reference_ffid ? `Recorder FFID ${record.reference_ffid}` : "This recorder record";
  const distance = metres(m.distance_m) ?? metres(record?.distance_m);
  switch (finding.code) {
    case "TARGET_ONLY": {
      const before = m.previous_reference_ffid, after = m.next_reference_ffid;
      const where = before && after ? `It lies between recorder FFID ${before} and ${after}.` : before ? `It lies after recorder FFID ${before}, the last recorded shot.` : after ? `It lies before recorder FFID ${after}, the first recorded shot.` : undefined;
      const noShots = count(m.no_shot_rows);
      return { text: "EIVA position has no recorder counterpart. This row will not be included in the corrected EIVA file.", detail: [where, noShots ? `${plural(noShots, "recorder no-shot row")} ${noShots === 1 ? "lies" : "lie"} in the same gap.` : undefined].filter(Boolean).join(" ") || undefined };
    }
    case "TARGET_ONLY_BLOCK": {
      const rows = count(m.rows);
      return { text: `${rows ? plural(rows, "consecutive EIVA position") : "Several consecutive EIVA positions"} have no recorder counterpart.`, detail: "These rows will not be included in the corrected EIVA file." };
    }
    case "ASSOCIATION_BLOCKED": {
      const nearest = typeof m.nearest_distance_m === "number" ? m.nearest_distance_m : null;
      const shifted = count(m.shift_records);
      const detail = nearest !== null
        ? `The nearest EIVA position is approximately ${roughMetres(nearest)} away${shifted ? `, and matching it would move ${plural(shifted, "other recorder record")} by one EIVA row` : ""}, so this recorder record was left unmatched for review.`
        : "No free EIVA position lies nearby in shot order, so this recorder record was left unmatched for review.";
      return { text: `${recorder} could not be matched to a nearby EIVA position.`, detail: `${detail} It is not in the corrected EIVA file.` };
    }
    case "RECORDER_FFID_DISCONTINUITY":
    case "TARGET_FFID_DISCONTINUITY": {
      const who = finding.code === "RECORDER_FFID_DISCONTINUITY" ? "Recorder" : "EIVA";
      const from = count(m.from), to = count(m.to);
      if (from === null || to === null) return { text: operatorWording(finding.message) };
      if (m.kind === "REVERSAL") return { text: `${who} FFID sequence goes back from ${from} to ${to}.` };
      const missing = to - from - 1;
      return { text: `${who} FFID sequence jumps from ${from} to ${to}.`, detail: missing > 0 ? `${plural(missing, "FFID")} ${missing === 1 ? "is" : "are"} skipped.` : undefined };
    }
    case "RECORDER_POSITION_JUMP":
    case "TARGET_POSITION_JUMP": {
      const who = finding.code.startsWith("RECORDER") ? "Recorder" : "EIVA";
      const intervals = count(m.intervals);
      return { text: `${who} position jumps ${distance ?? "a large distance"} from the previous shot${intervals ? ` (about ${Math.round(intervals)} shot intervals)` : ""}.` };
    }
    case "RECORDER_POSITION_SPIKE":
    case "TARGET_POSITION_SPIKE":
      return { text: `${finding.code.startsWith("RECORDER") ? "Recorder" : "EIVA"} position is ${distance ?? "far"} off the line and then returns to it.`, detail: "Check this coordinate." };
    case "RECORDER_DUPLICATE_COORDINATE":
    case "TARGET_DUPLICATE_COORDINATE":
      return { text: `${finding.code.startsWith("RECORDER") ? "Recorder" : "EIVA"} position repeats the previous shot's coordinate.` };
    case "RECORDER_SPACING_IRREGULAR":
    case "TARGET_SPACING_IRREGULAR": {
      const who = finding.code.startsWith("RECORDER") ? "Recorder" : "EIVA";
      const many = count(m.count);
      if (many !== null) return { text: `${plural(many, `${who.toLowerCase()} shot spacing`)} differ clearly from the shot interval.`, detail: "Check the Shot Interval in Settings." };
      return { text: `${who} shot spacing here is ${distance ?? "irregular"}${shotInterval ? `, against a ${shotInterval} m shot interval` : ""}.` };
    }
    case "RECORDER_DUPLICATE_FFID":
    case "TARGET_DUPLICATE_FFID":
      return { text: `${finding.code.startsWith("RECORDER") ? "Recorder" : "EIVA"} FFID ${m.ffid ?? ""} appears more than once.`.replace("  ", " "), detail: m.first_line ? `It first appears at line ${m.first_line}.` : undefined };
    case "RECORDER_NO_SHOT_ROW":
      return { text: `${recorder} is marked as "no shot" and is not treated as a recorded shot.` };
    case "SHOT_INTERVAL_MISMATCH": {
      const entered = count(m.entered_m), typical = count(m.median_spacing_m);
      return { text: `The Shot Interval${entered ? ` (${entered} m)` : ""} differs from the typical recorder spacing${typical ? ` (${typical.toFixed(3)} m)` : ""}.`, detail: "Distance checks may be misleading. Check the Shot Interval in Settings." };
    }
    case "ASSOCIATION_DISTANCE_ELEVATED":
      return { text: `Matched EIVA position is ${distance ?? "slightly"} away, a little more than normal.` };
    case "ASSOCIATION_DISTANCE_LARGE":
      return { text: `Matched EIVA position is ${distance ?? "far"} away, more than one shot interval.` };
    case "ASSOCIATION_DISTANCE_SEVERE":
      return { text: `Matched EIVA position is ${distance ?? "very far"} away.`, detail: "Check the recorder coordinate." };
    case "ASSOCIATION_SEQUENCE_ONLY":
      return { text: "Matched by shot order, not by position.", detail: m.distance_m === null || m.distance_m === undefined ? "The EIVA row has no usable position." : `The positions are ${distance} apart, too far to compare reliably.` };
    case "ASSOCIATION_AMBIGUOUS":
      return { text: "Other EIVA positions are about as close as the matched one.", detail: "The match that keeps shot order was used." };
    case "ASSOCIATION_NEAREST_OVERRIDDEN": {
      const nearest = metres(m.nearest_distance_m), assigned = metres(m.assigned_distance_m) ?? distance;
      return { text: `A closer EIVA position${nearest ? ` (${nearest})` : ""} is matched to a neighbouring shot; this match is ${assigned ?? "further"} away.` };
    }
    case "ASSOCIATION_RUN_DISPLACED": {
      const records = count(m.records);
      const assigned = metres(m.median_assigned_distance_m), nearest = metres(m.median_nearest_distance_m);
      const start = record?.reference_ffid ? ` from recorder FFID ${record.reference_ffid} onward` : "";
      return { text: `${records ? plural(records, "shot") : "Several shots"}${start} are each matched one EIVA position away from the closest one${assigned && nearest ? ` (typically ${assigned} instead of ${nearest})` : ""}.`, detail: "The two logs may be offset by one shot here. Review before saving." };
    }
    default:
      return { text: operatorWording(finding.message) };
  }
}

/** One readable line for a result row: its first (most severe) finding, or the association when there is none. */
export function describeRecord(record: EngineRecord, findings: QcFinding[], shotInterval?: number): QcDescription | null {
  if (findings.length) return describeFinding(findings[0], record, shotInterval);
  if (record.association === "TARGET_ONLY") return describeFinding({ code: "TARGET_ONLY", message: "", metrics: {} }, record);
  if (record.association === "BLOCKED") return describeFinding({ code: "ASSOCIATION_BLOCKED", message: "", metrics: {} }, record);
  return null;
}
