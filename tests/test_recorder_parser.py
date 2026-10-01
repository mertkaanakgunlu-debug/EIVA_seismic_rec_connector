from shotlogfixer.parsers import parse_recorder


def test_header_after_blank_lines_and_source_lines(tmp_path):
    path = tmp_path / "recorder.txt"
    path.write_text("\n\n  FFID SOU_X SOU_Y\n101 1 2\n", encoding="utf-8")
    rows = parse_recorder(path)
    assert len(rows) == 1
    assert rows[0].source_line_number == 4
    assert rows[0].coordinates_valid


def test_invalid_coordinate_variants_are_parsed_explicitly(tmp_path):
    path = tmp_path / "recorder.txt"
    path.write_text("1 -214748.36480 -214748.36480\n2 -214748.36480 1\n3 1 -214748.36480\n4 NaN 1\n5 1 Infinity\n", encoding="utf-8")
    rows = parse_recorder(path)
    assert [row.coordinates_valid for row in rows] == [False] * 5
