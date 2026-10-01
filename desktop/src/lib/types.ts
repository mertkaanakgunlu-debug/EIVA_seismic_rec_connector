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
  recorder_gap_count?: number;
  unexplained_missing_positions?: number;
}

export interface RecorderGapEvent {
  event_id: string;
  left_recorder_source_index: number;
  right_recorder_source_index: number;
  left_recorder_ffid: string;
  right_recorder_ffid: string;
  left_x: number;
  left_y: number;
  right_x: number;
  right_y: number;
  distance_m: number;
  shot_interval_m: number;
  match_tolerance_m: number;
  gap_span_steps: number;
  estimated_missing_positions: number;
  explicit_no_shot_count: number;
  invalid_between_count: number;
  unexplained_missing_positions: number;
  left_eiva_source_index: number | null;
  right_eiva_source_index: number | null;
  intermediate_eiva_indices: number[];
  eiva_only_indices: number[];
  no_shot_eiva_indices: number[];
  slot_assignments: Record<string, number>;
  classification: string;
  diagnostic: string;
  blocks_correction: boolean;
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
  gap_event_ids: string[];
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
  gap_event_id?: string | null;
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
  parameters: { shot_interval_m: number; match_tolerance_m: number; recorder_gap_threshold_m: number };
  recorder_gaps: RecorderGapEvent[];
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
