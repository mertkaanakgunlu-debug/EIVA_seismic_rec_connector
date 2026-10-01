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

@dataclass
class RecorderRecord:
    source_line_number: int
    ffid: str
    source_x: float
    source_y: float
    coordinates_valid: bool

@dataclass
class MatchResult:
    eiva_record: Optional[EivaRecord]
    recorder_record: Optional[RecorderRecord]
    distance_m: Optional[float]
    status: str
    diagnostic: str
