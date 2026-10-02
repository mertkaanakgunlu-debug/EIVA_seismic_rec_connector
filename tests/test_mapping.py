"""Stage A: profile-driven normalisation of both inputs into role-tagged records."""
import pytest

from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.canonical_mapping import parse_canonical
from shotlogfixer.format_profiles import FormatProfile, Structure, builtin_profiles
from shotlogfixer.models import REFERENCE, TARGET
from shotlogfixer.profile_validation import usable, validate_profile
from shotlogfixer.table_parser import parse_table

EIVA, RECORDER, PRONAV = builtin_profiles()


def test_profile_slots_map_to_workflow_roles():
    assert EIVA.workflow_role == "TARGET" and RECORDER.workflow_role == "REFERENCE" and PRONAV.workflow_role == "REFERENCE"


def test_reference_classification_variants():
    text = ("FFID SOU_X SOU_Y\n"
            "1 -214748.36480 -214748.36480\n"      # explicit no-shot marker
            "2 -214748.36480 1\n3 1 -214748.36480\n"  # only one sentinel
            "4 NaN 1\n5 1 Infinity\n6 1\n"            # unusable coordinates
            "x 2 3\n7.5 2 3\n"                        # FFID is not an integer
            "8 2 3\n")
    records = parse_canonical(text, RECORDER)
    assert [r.classification for r in records] == ["NO_SHOT", "INVALID", "INVALID", "INVALID", "INVALID", "INVALID",
                                                    "INVALID", "INVALID", "VALID"]
    assert all(r.role == REFERENCE for r in records)
    assert records[-1].authoritative_ffid == "8" and records[0].authoritative_ffid is None
    assert "sentinel" in records[1].invalid_reason and "integer" in records[6].invalid_reason


def test_reference_header_after_blank_lines_keeps_source_line_numbers():
    records = parse_canonical("\n\n  FFID SOU_X SOU_Y\n101 1 2\n", RECORDER)
    assert len(records) == 1 and records[0].source_line_number == 4 and records[0].classification == "VALID"
    assert records[0].columns == ("FFID", "SOU_X", "SOU_Y") and records[0].row_index == 0


def test_target_ffid_is_a_diagnostic_so_any_text_is_accepted():
    records = parse_canonical("FFID,E(Spark),N(Spark)\nL1-0001,1,2\n,3,4\n  7 ,5,6\n", EIVA)
    assert [r.classification for r in records] == ["VALID"] * 3
    assert [r.original_ffid for r in records] == ["L1-0001", "", "7"]
    assert all(r.role == TARGET and r.authoritative_ffid is None for r in records)


def test_target_rows_with_unusable_coordinates_are_kept_not_fatal():
    records = parse_canonical("FFID,E(Spark),N(Spark)\n1,10,20\n2,oops,30\n3,12,\n4,13,40\n", EIVA)
    assert [r.classification for r in records] == ["VALID", "INVALID", "INVALID", "VALID"]
    assert records[1].x is None and "not a finite number" in records[1].invalid_reason
    assert [r.row_index for r in records] == [0, 1, 2, 3]


def test_short_target_row_without_an_ffid_cell_is_flagged_not_dropped():
    profile = FormatProfile("t", "t", "EIVA", Structure("comma", "ABSENT"),
                            (("EIVA_EASTING", 0), ("EIVA_NORTHING", 1), ("FFID", 3)))
    records = parse_canonical("1,2,3,100\n4,5\n", profile)
    assert [r.ffid_cell_present for r in records] == [True, False]
    assert records[1].has_position and records[1].original_ffid == ""


def test_profile_validation_requires_numeric_reference_ffid_but_not_target_ffid():
    reference_text = "FFID SOU_X SOU_Y\n" + "".join(f"L{i} 1 2\n" for i in range(5))
    target_text = "FFID,E(Spark),N(Spark)\n" + "".join(f"L{i},1,2\n" for i in range(5))
    assert not validate_profile(RECORDER, parse_table(reference_text, RECORDER))["valid"]
    assert validate_profile(EIVA, parse_table(target_text, EIVA))["valid"]
    assert usable(["L1", "1", "2"], EIVA) and not usable(["L1", "1", "2"], RECORDER)


def test_alternate_delimiters_and_columns_need_no_code_change():
    # Easting/Northing/FFID in other columns, semicolon delimited, with a preamble line.
    profile = FormatProfile("t", "t", "EIVA", Structure("semicolon", "PRESENT", skip_rows=1),
                            (("EIVA_EASTING", 4), ("EIVA_NORTHING", 5), ("FFID", 7)))
    text = "PROJECT;X\nDate;Time;Line;Point;Easting;Northing;Elev;FFID\n2025;1;L1;5;615190.2;4645679.7;0;9001\n"
    (record,) = parse_canonical(text, profile)
    assert (record.x, record.y, record.original_ffid) == (615190.2, 4645679.7, "9001")
    assert record.source_line_number == 3


def test_parameters_are_qc_bands_not_a_match_tolerance():
    params = AnalysisParameters(3.125)
    assert (params.normal_distance_m, params.elevated_distance_m, params.severe_distance_m) == (1.5625, 3.125, 15.625)
    assert (params.jump_distance_m, params.severe_jump_distance_m) == (15.625, 62.5)
    assert params.alignment_cap_m == params.severe_distance_m
    assert not hasattr(params, "match_tolerance_m")
    for value in (None, "", 0, -1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            AnalysisParameters(value)


def test_target_row_without_an_ffid_cell_is_still_usable_for_validation():
    profile = FormatProfile("t", "t", "EIVA", Structure("comma", "ABSENT"),
                            (("EIVA_EASTING", 0), ("EIVA_NORTHING", 1), ("FFID", 3)))
    assert usable(["1", "2"], profile)                       # the FFID is only a diagnostic for the target
    assert not usable(["1"], profile)                        # but the coordinates are required
