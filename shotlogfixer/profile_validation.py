import math
from .format_profiles import ROLES


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError): return None


def usable(cells, profile):
    """A row is usable when its mapped coordinates are numeric.

    The reference input's FFID is authoritative, so it must be an integer.  The target's own FFID is
    only a diagnostic (the corrected copy overwrites it), so any text is acceptable there."""
    try:
        ffid_role, x_role, y_role = ROLES[profile.input_type]
        if profile.workflow_role == "REFERENCE":
            ffid = finite(cells[profile.mapping[ffid_role]])
            if ffid is None or not ffid.is_integer(): return False
        # A target row without an FFID cell is still usable: it is reported later and only blocks if it must be written.
        return all(finite(cells[profile.mapping[role]]) is not None for role in (x_role, y_role))
    except (IndexError, KeyError, TypeError, AttributeError): return False


def validate_profile(profile, table, require_confirmation=False):
    errors = []
    try: profile.check_syntax()
    except ValueError as exc: errors.append(str(exc))
    if any(i >= table.column_count for i in profile.mapping.values()): errors.append("Profile references a non-existent column")
    good = sum(usable(row.cells, profile) for row in table.rows)
    total = len(table.rows)
    if not total or not good or good / total < .8:
        errors.append(f"{good} usable coordinate rows from {total} data rows. Review delimiter, header and column mapping.")
    if require_confirmation and profile.confidence != "High confidence" and not profile.confirmed:
        errors.append("Format interpretation requires operator confirmation")
    return {"valid": not errors, "usable_rows": good, "data_rows": total,
            "errors": errors, "warnings": list(profile.warnings)}


def require_valid(profile, table):
    result = validate_profile(profile, table, True)
    if not result["valid"]: raise ValueError("Format not ready: " + '; '.join(result["errors"]))
    return result
