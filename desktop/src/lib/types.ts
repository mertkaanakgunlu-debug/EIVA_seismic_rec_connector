/** Correction decision for one result row. Independent of QC: a QC finding never changes it. */
export const ASSOCIATIONS = ["ASSIGNED", "TARGET_ONLY", "INVALID", "NO_SHOT", "BLOCKED"] as const;
export type Association = (typeof ASSOCIATIONS)[number];
export type QcSeverity = "OK" | "INFO" | "WARNING" | "SEVERE";

export interface AnalysisSummary {
  reference_rows: number;
  reference_valid: number;
  reference_no_shot: number;
  reference_invalid: number;
  target_rows: number;
  target_invalid: number;
  assigned: number;
  target_only: number;
  invalid_target_removed: number;
  blocked: number;
  corrected_rows: number;
  expected_rows: number;
  qc_info: number;
  qc_warning: number;
  qc_severe: number;
  assigned_with_warning: number;
  assigned_with_severe: number;
}

/** One acquisition-ordered row: an association (pair), a target-only row, or a reference record without a target row. */
export interface EngineRecord {
  id: string;
  acquisition_position: number;
  association: Association;
  reference_ffid: string | null;
  reference_line: number | null;
  reference_x: number | null;
  reference_y: number | null;
  target_ffid: string | null;
  target_line: number | null;
  target_x: number | null;
  target_y: number | null;
  corrected_ffid: string | null;
  distance_m: number | null;
  basis: "SPATIAL" | "SEQUENCE" | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | null;
  qc_severity: QcSeverity;
  qc_codes: string[];
  diagnostic: string;
  target_values: Record<string, string>;
}

export interface QcFinding {
  scope: "RECORDER" | "TARGET" | "ASSOCIATION";
  code: string;
  severity: Exclude<QcSeverity, "OK">;
  message: string;
  reference_row: number | null;
  target_row: number | null;
  row_id: string | null;
  metrics: Record<string, unknown>;
}

export interface FfidJump {
  from: number | null;
  to: number | null;
  kind: "GAP" | "REVERSAL" | null;
  row_id: string | null;
}

export interface CorrectionBlocker {
  code: string;
  message: string;
}

/** Only structural impossibilities block a corrected copy; QC warnings never do. */
export interface CorrectionSummary {
  safe: boolean;
  blockers: CorrectionBlocker[];
  assigned: number;
  target_only_removed: number;
  invalid_target_removed: number;
  corrected_rows: number;
  expected_rows: number;
  direction: string;
}

export interface ValidationSummary {
  passed: boolean;
  errors: string[];
  corrected_rows: number;
  expected_rows: number;
  ffid_changed: number;
  ffid_unchanged: number;
  checks: Record<string, boolean>;
}

export interface QcSummary {
  total: number;
  by_severity: Record<string, number>;
  by_scope: Record<string, number>;
  by_code: Record<string, number>;
}

export interface AnalysisParameters {
  shot_interval_m: number;
  normal_distance_m: number;
  elevated_distance_m: number;
  severe_distance_m: number;
  jump_distance_m: number;
  severe_jump_distance_m: number;
}

export interface AnalysisSuccess {
  ok: true;
  summary: AnalysisSummary;
  records: EngineRecord[];
  correction: CorrectionSummary;
  validation: ValidationSummary;
  qc: { summary: QcSummary; findings: QcFinding[]; ffid_jumps: FfidJump[] };
  input_hashes?: { reference: string; target: string };
  parameters: AnalysisParameters;
  target_headers: string[];
  input_formats?: { reference: FormatProfileSummary; target: FormatProfileSummary };
}

export interface FormatProfileSummary {
  id: string;
  name: string;
  confidence: string;
  delimiter: string;
  header: string;
  profile_hash: string;
  column_mapping: Record<string, number>;
  [key: string]: unknown;
}

export interface AnalysisFailure {
  ok: false;
  error: { code: string; message: string; detail?: string };
}

export type AnalysisResponse = AnalysisSuccess | AnalysisFailure;

export interface ExportResponse {
  ok: boolean;
  path?: string;
  error?: { code: string; message: string; detail?: string };
}
