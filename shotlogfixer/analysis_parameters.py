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

    def as_dict(self):
        return {"shot_interval_m": self.shot_interval_m,
                "match_tolerance_m": self.match_tolerance_m}
