"""Immutable acquisition settings shared by alignment, QC and correction.

The shot interval describes *normal acquisition geometry*.  It sets QC bands and
the distance beyond which spatial evidence stops discriminating between
candidates.  It is never an existence test: no distance derived from it can
discard an authoritative reference record.
"""

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

    # --- association distance QC bands (reference -> target) -------------------------------
    @property
    def normal_distance_m(self) -> float:
        """Association distance up to half an interval is normal."""
        return self.shot_interval_m / 2

    @property
    def elevated_distance_m(self) -> float:
        """Up to one interval is elevated; beyond it the association is large."""
        return self.shot_interval_m

    @property
    def severe_distance_m(self) -> float:
        """Beyond five intervals the association distance is severe."""
        return self.shot_interval_m * 5

    # --- position-step QC (consecutive records of one input) -------------------------------
    @property
    def jump_distance_m(self) -> float:
        return self.shot_interval_m * 5

    @property
    def severe_jump_distance_m(self) -> float:
        return self.shot_interval_m * 20

    # --- alignment ------------------------------------------------------------------------
    @property
    def alignment_cap_m(self) -> float:
        """Spatial evidence saturates here.  A larger distance still counts as "far", but it
        no longer prefers one candidate over another, so an anomalous coordinate cannot drag
        its neighbours' assignments; sequence continuity decides instead.  Nothing is rejected."""
        return self.severe_distance_m

    def as_dict(self):
        return {"shot_interval_m": self.shot_interval_m,
                "normal_distance_m": self.normal_distance_m,
                "elevated_distance_m": self.elevated_distance_m,
                "severe_distance_m": self.severe_distance_m,
                "jump_distance_m": self.jump_distance_m,
                "severe_jump_distance_m": self.severe_jump_distance_m}


@dataclass(frozen=True)
class AnalysisConfiguration:
    """Complete reproducible analysis input, including format interpretation."""
    parameters: AnalysisParameters
    reference_profile: object
    target_profile: object

    @property
    def reference_profile_hash(self): return self.reference_profile.profile_hash

    @property
    def target_profile_hash(self): return self.target_profile.profile_hash

    def as_dict(self):
        return {**self.parameters.as_dict(), "reference_profile": self.reference_profile.as_dict(),
                "target_profile": self.target_profile.as_dict(),
                "reference_profile_hash": self.reference_profile_hash,
                "target_profile_hash": self.target_profile_hash}
