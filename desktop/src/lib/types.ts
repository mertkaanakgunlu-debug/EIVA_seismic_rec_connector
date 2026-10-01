export const STATUSES = ["MATCHED", "EIVA_ONLY", "RECORDER_INVALID", "REVIEW"] as const;
export type Status = (typeof STATUSES)[number];

export interface AnalysisSummary {
  eiva_rows: number;
  recorder_rows: number;
  matched: number;
  eiva_only: number;
  recorder_invalid: number;
  review: number;
  total_issues: number;
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

export interface AnalysisSuccess {
  ok: true;
  summary: AnalysisSummary;
  ffid_jumps: Array<{ from: string; to: string }>;
  eiva_headers: string[];
  records: EngineRecord[];
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
