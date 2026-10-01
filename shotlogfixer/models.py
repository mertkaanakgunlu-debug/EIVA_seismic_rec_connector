from dataclasses import dataclass, field
from typing import Optional, Any

@dataclass
class EivaRecord:
    source_line_number: int
    original_ffid: str
    easting_spark: float
    northing_spark: float
    original_fields: list[str]
    original_values_by_column: dict[str, str] = field(default_factory=dict)
    original_line: str = ""
    source_end_line_number: Optional[int] = None

@dataclass
class RecorderRecord:
    source_line_number: int
    ffid: str
    source_x: Optional[float]
    source_y: Optional[float]
    coordinates_valid: bool
    original_fields: list[str] = field(default_factory=list)
    original_line: str = ""
    classification: str = "INVALID"
    header_fields: list[str] = field(default_factory=list)

    @property
    def row_classification(self) -> str:
        return self.classification

@dataclass
class MatchResult:
    eiva_record: Optional[EivaRecord]
    recorder_record: Optional[RecorderRecord]
    distance_m: Optional[float]
    status: str
    diagnostic: str


@dataclass
class CorrectionAction:
    action_type: str
    eiva_source_index: Optional[int] = None
    original_eiva_ffid: Optional[str] = None
    target_ffid: Optional[str] = None
    recorder_source_index: Optional[int] = None
    recorder_ffid: Optional[str] = None
    status: str = ""
    reason: str = ""
    coordinate_distance_m: Optional[float] = None


@dataclass
class CorrectionPlan:
    actions: list[CorrectionAction] = field(default_factory=list)
    matched_count: int = 0
    dropped_eiva_only_count: int = 0
    dropped_no_shot_count: int = 0
    unresolved_count: int = 0
    invalid_recorder_count: int = 0
    source_eiva_count: int = 0
    source_recorder_count: int = 0
    planned_fixed_eiva_count: int = 0
    planned_fixed_recorder_count: int = 0
    safe_to_build: bool = False
    blocking_reasons: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    passed: bool
    source_eiva_count: int = 0
    source_recorder_count: int = 0
    valid_recorder_count: int = 0
    no_shot_recorder_count: int = 0
    invalid_recorder_count: int = 0
    fixed_eiva_count: int = 0
    fixed_recorder_count: int = 0
    ffid_pair_count: int = 0
    ffid_match_count: int = 0
    coordinate_pass_count: int = 0
    max_distance_m: Optional[float] = None
    mean_distance_m: Optional[float] = None
    median_distance_m: Optional[float] = None
    above_tolerance_count: int = 0
    duplicate_ffids: list[str] = field(default_factory=list)
    duplicate_source_mappings: list[str] = field(default_factory=list)
    missing_ffids: list[str] = field(default_factory=list)
    extra_ffids: list[str] = field(default_factory=list)
    non_monotonic_mapping_count: int = 0
    no_shot_rows_remaining: int = 0
    invalid_rows_remaining: int = 0
    unresolved_review_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "source_eiva_count": self.source_eiva_count,
            "source_recorder_count": self.source_recorder_count,
            "valid_recorder_count": self.valid_recorder_count,
            "no_shot_recorder_count": self.no_shot_recorder_count,
            "invalid_recorder_count": self.invalid_recorder_count,
            "fixed_eiva_rows": self.fixed_eiva_count,
            "fixed_recorder_rows": self.fixed_recorder_count,
            "ffid_pair_count": self.ffid_pair_count,
            "ffid_match_count": self.ffid_match_count,
            "coordinate_pass_count": self.coordinate_pass_count,
            "max_distance_m": self.max_distance_m,
            "mean_distance_m": self.mean_distance_m,
            "median_distance_m": self.median_distance_m,
            "above_tolerance_count": self.above_tolerance_count,
            "duplicate_ffids": self.duplicate_ffids,
            "duplicate_source_mappings": self.duplicate_source_mappings,
            "missing_ffids": self.missing_ffids,
            "extra_ffids": self.extra_ffids,
            "non_monotonic_mapping_count": self.non_monotonic_mapping_count,
            "no_shot_rows_remaining": self.no_shot_rows_remaining,
            "invalid_rows_remaining": self.invalid_rows_remaining,
            "unresolved_review_count": self.unresolved_review_count,
            "errors": self.errors,
            "warnings": self.warnings,
        }
