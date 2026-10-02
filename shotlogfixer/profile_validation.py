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
        values = [cells[profile.mapping[role]] for role in ROLES[profile.input_type]]
        if profile.workflow_role == "REFERENCE":
            ffid = finite(values[0])
            if ffid is None or not ffid.is_integer(): return False
        return all(finite(v) is not None for v in values[1:])
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
