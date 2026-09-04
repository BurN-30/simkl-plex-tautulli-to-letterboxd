"""The Letterboxd CSV dialect: escaping, quoting, splitting."""

from __future__ import annotations

import pytest

from src.letterboxd import csv_format


class TestFieldFormatting:
    def test_plain_value_is_not_quoted(self):
        assert csv_format.format_field("Gremlins") == "Gremlins"

    def test_none_and_empty_render_as_empty(self):
        assert csv_format.format_field(None) == ""
        assert csv_format.format_field("") == ""

    def test_numbers_are_stringified(self):
        assert csv_format.format_field(1984) == "1984"

    def test_comma_forces_quotes(self):
        assert csv_format.format_field("Paris, Texas") == '"Paris, Texas"'

    def test_quote_is_escaped_with_a_backslash_not_doubled(self):
        # Letterboxd: "escape quotes within quoted text, by prefixing them
        # with a backslash (\) character". csv.writer would produce "" here.
        assert csv_format.format_field('He said "hi"') == '"He said \\"hi\\""'

    def test_newline_forces_quotes_and_is_preserved(self):
        assert csv_format.format_field("line one\nline two") == '"line one\nline two"'

    def test_carriage_return_forces_quotes(self):
        assert csv_format.format_field("a\r\nb") == '"a\r\nb"'

    def test_backslash_is_escaped(self):
        assert csv_format.format_field("back\\slash") == '"back\\\\slash"'

    def test_leading_and_trailing_space_is_quoted(self):
        # Letterboxd warns that a space next to a comma breaks quoted parsing.
        assert csv_format.format_field(" padded ") == '" padded "'

    def test_directors_list_matches_the_official_example(self):
        assert csv_format.format_field("Joel Coen, Ethan Coen") == '"Joel Coen, Ethan Coen"'


class TestRowRendering:
    def test_official_example_line(self):
        assert csv_format.format_row(["Paris, Texas", 1984, 4]) == '"Paris, Texas",1984,4'

    def test_document_uses_lf_endings_and_trailing_newline(self):
        text = csv_format.render(["Title", "Year"], [["Top Gun", 1986]])
        assert text == "Title,Year\nTop Gun,1986\n"
        assert "\r\n" not in text


class TestParsing:
    def test_reads_back_escaped_quotes(self):
        rows = csv_format.parse('Title\n"He said \\"hi\\""\n')
        assert rows == [["Title"], ['He said "hi"']]

    def test_reads_back_embedded_newline_as_one_field(self):
        rows = csv_format.parse('Review\n"line one\nline two"\n')
        assert rows == [["Review"], ["line one\nline two"]]

    def test_empty_fields_are_kept(self):
        assert csv_format.parse("a,,c\n") == [["a", "", "c"]]

    def test_no_phantom_row_after_trailing_newline(self):
        assert csv_format.parse("a,b\n") == [["a", "b"]]

    def test_last_line_without_newline_is_kept(self):
        assert csv_format.parse("a,b\nc,d") == [["a", "b"], ["c", "d"]]

    @pytest.mark.parametrize(
        "value",
        [
            "plain",
            "Paris, Texas",
            'quote " inside',
            'ends with a quote"',
            "back\\slash",
            "trailing backslash\\",
            "multi\nline\nreview",
            " padded ",
            "accents: éàçüñ 日本語",
            'nested \\" sequence',
            "",
        ],
    )
    def test_round_trip_is_exact(self, value):
        text = csv_format.render(["Value"], [[value]])
        assert csv_format.parse(text)[1] == [value]

    def test_parse_dicts_uses_the_header_row(self):
        text = csv_format.render(["Title", "Year"], [["Top Gun", 1986]])
        assert csv_format.parse_dicts(text) == [{"Title": "Top Gun", "Year": "1986"}]

    def test_parse_dicts_skips_blank_lines(self):
        assert csv_format.parse_dicts("Title,Year\n\nTop Gun,1986\n") == [
            {"Title": "Top Gun", "Year": "1986"}
        ]


class TestSplitting:
    HEADERS = ["Title", "Review"]

    def _rows(self, count, review_size):
        return [[f"Film {index}", "x" * review_size] for index in range(count)]

    def test_small_export_is_a_single_chunk(self):
        chunks = csv_format.split_rows(self.HEADERS, self._rows(10, 10))
        assert len(chunks) == 1

    def test_chunks_stay_under_the_limit_header_included(self):
        max_bytes = 4_000
        rows = self._rows(100, 200)
        chunks = csv_format.split_rows(self.HEADERS, rows, max_bytes=max_bytes)
        assert len(chunks) > 1
        header_size = len(csv_format.format_row(self.HEADERS).encode()) + 1
        for chunk in chunks:
            size = header_size + sum(len(line.encode()) + 1 for line in chunk)
            assert size <= max_bytes

    def test_no_row_is_lost_when_splitting(self):
        rows = self._rows(50, 300)
        chunks = csv_format.split_rows(self.HEADERS, rows, max_bytes=3_000)
        assert sum(len(chunk) for chunk in chunks) == len(rows)

    def test_oversized_single_row_gets_its_own_chunk(self):
        rows = [["Small", "x" * 10], ["Huge", "y" * 5_000], ["Small again", "z" * 10]]
        chunks = csv_format.split_rows(self.HEADERS, rows, max_bytes=1_000)
        assert [len(chunk) for chunk in chunks] == [1, 1, 1]

    def test_default_threshold_is_below_the_letterboxd_limit(self):
        assert csv_format.DEFAULT_MAX_FILE_BYTES < csv_format.LETTERBOXD_MAX_FILE_BYTES


class TestWriting:
    def test_single_file_has_no_part_suffix(self, tmp_path):
        paths = csv_format.write_chunked(tmp_path, "watched", ["Title"], [["Top Gun"]])
        assert [path.name for path in paths] == ["watched.csv"]

    def test_multiple_files_are_numbered_and_repeat_the_header(self, tmp_path):
        rows = [[f"Film {index}", "x" * 300] for index in range(40)]
        paths = csv_format.write_chunked(
            tmp_path, "watched", ["Title", "Review"], rows, max_bytes=2_000
        )
        assert len(paths) > 1
        assert [path.name for path in paths] == [
            f"watched_part{index:02d}.csv" for index in range(1, len(paths) + 1)
        ]
        for path in paths:
            assert path.read_text(encoding="utf-8").startswith("Title,Review\n")
            assert path.stat().st_size <= 2_000

    def test_files_are_utf8_without_bom_and_lf_only(self, tmp_path):
        paths = csv_format.write_chunked(
            tmp_path, "watched", ["Title"], [["Amélie"], ["Paris, Texas"]]
        )
        raw = paths[0].read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert "Amélie" in raw.decode("utf-8")

    def test_no_file_is_written_when_there_are_no_rows(self, tmp_path):
        assert csv_format.write_chunked(tmp_path, "watched", ["Title"], []) == []
        assert list(tmp_path.glob("*.csv")) == []

    def test_every_row_survives_a_write_read_cycle(self, tmp_path):
        rows = [[f"Film {index}", 'a "quoted, review"\nsecond line'] for index in range(30)]
        paths = csv_format.write_chunked(
            tmp_path, "watched", ["Title", "Review"], rows, max_bytes=1_500
        )
        recovered = []
        for path in paths:
            recovered.extend(csv_format.parse_dicts(path.read_text(encoding="utf-8")))
        assert len(recovered) == len(rows)
        assert recovered[0]["Review"] == 'a "quoted, review"\nsecond line'
