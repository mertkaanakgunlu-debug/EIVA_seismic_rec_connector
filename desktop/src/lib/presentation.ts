import type { Status } from "./types";

const RECORD_LABELS: Record<Status, string> = {
  MATCHED: "Matched", EIVA_ONLY: "EIVA only", NO_SHOT: "Not recorded",
  RECORDER_INVALID: "Invalid", REVIEW: "Review",
};
const GAP_LABELS: Record<string, string> = {
  RECORDER_GAP_SHARED: "Shared gap",
  RECORDER_GAP_WITH_EIVA_ONLY: "EIVA-only gap",
  RECORDER_GAP_EXPLAINED_BY_NO_SHOT: "Explained by not-recorded shot",
  RECORDER_GAP_MIXED: "Mixed",
  RECORDER_GAP_AMBIGUOUS: "Needs review",
};

export const formatRecordStatus = (status: Status): string => RECORD_LABELS[status];
export const formatGapClassification = (classification: string): string => GAP_LABELS[classification] || "Needs review";

/** Humanize diagnostic prose while canonical response fields remain unchanged. */
export function formatDiagnostic(text: string): string {
  const labels: Record<string, string> = { ...RECORD_LABELS, ...GAP_LABELS, INVALID: "Invalid", VALID: "valid" };
  return text.replace(/\b(?:RECORDER_GAP_[A-Z_]+|RECORDER_INVALID|EIVA_ONLY|NO_SHOT|MATCHED|REVIEW|INVALID|VALID)\b/g,
    (code) => labels[code] || "Needs review");
}
