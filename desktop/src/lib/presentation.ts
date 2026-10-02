import type { Association, EngineRecord, QcSeverity } from "./types";

const ASSOCIATION_LABELS: Record<Association, string> = {
  ASSIGNED: "Assigned", TARGET_ONLY: "Target-only", INVALID: "Invalid", NO_SHOT: "No shot", BLOCKED: "Blocked",
};
const SEVERITY_LABELS: Record<QcSeverity, string> = { OK: "OK", INFO: "Note", WARNING: "Warning", SEVERE: "Severe" };
const QC_LABELS: Record<string, string> = {
  RECORDER_INVALID_ROW: "Recorder row invalid",
  RECORDER_NO_SHOT_ROW: "Recorder no-shot row",
  RECORDER_DUPLICATE_FFID: "Duplicate recorder FFID",
  RECORDER_FFID_DISCONTINUITY: "Recorder FFID discontinuity",
  RECORDER_DUPLICATE_COORDINATE: "Recorder duplicate coordinate",
  RECORDER_POSITION_JUMP: "Recorder position jump",
  RECORDER_POSITION_SPIKE: "Recorder position spike",
  RECORDER_SPACING_IRREGULAR: "Recorder spacing irregular",
  SHOT_INTERVAL_MISMATCH: "Shot interval mismatch",
  TARGET_INVALID_ROW: "Target row invalid",
  TARGET_ONLY: "Target-only row",
  TARGET_ONLY_BLOCK: "Target-only block",
  TARGET_POSITION_JUMP: "Target position jump",
  TARGET_POSITION_SPIKE: "Target position spike",
  TARGET_DUPLICATE_COORDINATE: "Target duplicate coordinate",
  TARGET_SPACING_IRREGULAR: "Target spacing irregular",
  TARGET_DUPLICATE_FFID: "Duplicate target FFID",
  TARGET_FFID_DISCONTINUITY: "Target FFID discontinuity",
  ASSOCIATION_DISTANCE_ELEVATED: "Elevated distance",
  ASSOCIATION_DISTANCE_LARGE: "High distance",
  ASSOCIATION_DISTANCE_SEVERE: "Severe distance",
  ASSOCIATION_SEQUENCE_ONLY: "Placed by sequence",
  ASSOCIATION_AMBIGUOUS: "Ambiguous",
  ASSOCIATION_NEAREST_OVERRIDDEN: "Nearest row not used",
  ASSOCIATION_RUN_DISPLACED: "Displaced run",
  ASSOCIATION_BLOCKED: "Blocked",
};

const BLOCKER_LABELS: Record<string, string> = {
  REFERENCE_ROWS_INVALID: "Recorder rows cannot be interpreted",
  NO_REFERENCE_RECORDS: "No valid recorder records",
  NO_TARGET_ROWS: "No target rows",
  INSUFFICIENT_TARGET_ROWS: "Too few target rows for a one-to-one assignment",
  TARGET_FFID_FIELD_MISSING: "Target FFID field missing",
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
