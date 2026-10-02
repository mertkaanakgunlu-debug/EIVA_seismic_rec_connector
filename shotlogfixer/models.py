"""Role-neutral records shared by alignment, QC and correction.

The format layer is generic: any supported text file is parsed through a format
profile into ``SourceRecord`` objects.  The *workflow* is asymmetric and is
expressed by the role a record carries, never by a vendor-specific parser:

``REFERENCE``
    The authoritative dataset (the seismic recorder log).  A valid reference
    record means that seismic shot really exists and its FFID is authoritative.
``TARGET``
    The dataset being corrected (the EIVA/navigation log).  Its own FFIDs are
    diagnostics only; they never decide shot identity.
"""

from dataclasses import dataclass
from typing import Optional

REFERENCE = "REFERENCE"
TARGET = "TARGET"

# Record classification (reference rows use all three, target rows VALID/INVALID).
VALID = "VALID"
NO_SHOT = "NO_SHOT"      # reference row carrying the "no shot recorded" coordinate sentinel
INVALID = "INVALID"      # FFID or coordinates cannot be interpreted

# Association status of one result row (correction decision, independent of QC).
ASSIGNED = "ASSIGNED"            # a reference record was associated with a target row
TARGET_ONLY = "TARGET_ONLY"      # target row with no reference record: removed from the corrected copy
INVALID_ROW = "INVALID"          # row cannot take part (unparseable); never silently treated as a shot
NO_SHOT_ROW = "NO_SHOT"          # reference row explicitly marked "no shot"
BLOCKED = "BLOCKED"              # valid reference record that no target row can hold (not a correction blocker)

# QC severities, ordered.
INFO = "INFO"
WARNING = "WARNING"
SEVERE = "SEVERE"
SEVERITY_ORDER = {INFO: 1, WARNING: 2, SEVERE: 3}


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One data row of an imported file after profile-driven normalisation."""

    role: str
    row_index: int                 # zero-based position among this input's data rows
    source_line_number: int        # first physical line (1-based)
    source_end_line_number: int    # last physical line (quoted fields may span lines)
    raw: str                       # original text of the record, line endings included
    cells: tuple[str, ...]
    original_ffid: str             # as read from the mapped FFID column
    x: Optional[float]
    y: Optional[float]
    classification: str
    invalid_reason: str = ""
    ffid_cell_present: bool = True
    columns: tuple[str, ...] = ()

    @property
    def has_position(self) -> bool:
        return self.x is not None and self.y is not None

    @property
    def authoritative_ffid(self) -> Optional[str]:
        """The FFID the corrected target row receives; only valid reference rows carry one."""
        return self.original_ffid if self.role == REFERENCE and self.classification == VALID else None

    def values_by_column(self) -> dict[str, str]:
        return dict(zip(self.columns, self.cells))
