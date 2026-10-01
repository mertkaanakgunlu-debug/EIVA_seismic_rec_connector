"""Immutable acquisition settings shared by matching, correction and validation."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AnalysisParameters:
    shot_interval_m: float

    def __post_init__(self):
        if isinstance(self.shot_interval_m, bool):
            raise ValueError("Shot interval must be a finite positive number")
        try:
            value = float(self.shot_interval_m)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Shot interval must be a finite positive number") from exc
        if not math.isfinite(value) or value <= 0 or value / 2 == 0:
            raise ValueError("Shot interval must be a finite positive number")
        object.__setattr__(self, "shot_interval_m", value)

    @property
    def match_tolerance_m(self) -> float:
        return self.shot_interval_m / 2

    @property
    def recorder_gap_threshold_m(self) -> float:
        return self.shot_interval_m * 5

    def as_dict(self):
        return {"shot_interval_m": self.shot_interval_m,
                "match_tolerance_m": self.match_tolerance_m,
                "recorder_gap_threshold_m": self.recorder_gap_threshold_m}


@dataclass(frozen=True)
class AnalysisConfiguration:
    """Complete reproducible analysis input, including format interpretation."""
    parameters: AnalysisParameters
    eiva_profile: object
    recorder_profile: object

    @property
    def eiva_profile_hash(self): return self.eiva_profile.profile_hash

    @property
    def recorder_profile_hash(self): return self.recorder_profile.profile_hash

    def as_dict(self):
        return {**self.parameters.as_dict(), "eiva_profile": self.eiva_profile.as_dict(),
                "recorder_profile": self.recorder_profile.as_dict(),
                "eiva_profile_hash": self.eiva_profile_hash,
                "recorder_profile_hash": self.recorder_profile_hash}
