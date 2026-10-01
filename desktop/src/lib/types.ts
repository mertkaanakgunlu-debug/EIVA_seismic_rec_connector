export const STATUSES = ["MATCHED", "EIVA_ONLY", "NO_SHOT", "RECORDER_INVALID", "REVIEW"] as const;
export type Status = (typeof STATUSES)[number];

export interface AnalysisSummary {
  eiva_rows: number;
  recorder_rows: number;
  matched: number;
  eiva_only: number;
  recorder_invalid: number;
  review: number;
  total_issues: number;
  no_shot?: number;
}

export interface EngineRecord {
  id: string;
  result_index: number;
  acquisition_position: number;
  eiva_ffid: string | null;
  recorder_ffid: string | null;
  eiva_easting: number | null;
  eiva_northing: number | null;
  recorder_x: number | null;
  recorder_y: number | null;
  distance_m: number | null;
  status: Status;
  diagnostic: string;
  eiva_values: Record<string, string>;
}

export interface CorrectionAction {
  action: string;
  eiva_ffid: string | null;
  target_ffid: string | null;
  recorder_ffid: string | null;
  eiva_source_index: number | null;
  recorder_source_index: number | null;
  status: Status;
  reason: string;
  distance_m: number | null;
}

export interface CorrectionSummary {
  safe: boolean;
  retained: number;
  eiva_only_removed: number;
  no_shot_removed: number;
  blocking_reasons: string[];
  actions: CorrectionAction[];
}

export interface ValidationSummary {
  passed: boolean;
  fixed_eiva_rows: number;
  fixed_recorder_rows: number;
  ffid_pair_count: number;
  ffid_match_count: number;
  coordinate_pass_count: number;
  max_distance_m: number | null;
  mean_distance_m: number | null;
  median_distance_m: number | null;
  above_tolerance_count: number;
  errors: string[];
  [key: string]: unknown;
}

export interface AnalysisSuccess {
  ok: true;
  summary: AnalysisSummary;
  ffid_jumps: Array<{ from: string; to: string }>;
  eiva_headers: string[];
  records: EngineRecord[];
  correction: CorrectionSummary;
  validation: ValidationSummary;
  input_hashes?: { eiva: string; recorder: string };
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
