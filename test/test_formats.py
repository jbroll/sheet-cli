"""Unit tests for CLI format helpers."""

import os
import sys
import io

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import formats


class TestParseCellValuePairs:
    def test_basic(self):
        assert formats.parse_cell_value_pairs("A1 hello\nA2 123") == {
            'A1': 'hello',
            'A2': '123',
        }

    def test_multiword_value(self):
        assert formats.parse_cell_value_pairs("A1 hello world") == {
            'A1': 'hello world',
        }

    def test_formula_value(self):
        assert formats.parse_cell_value_pairs("A3 =SUM(A1:A2)") == {
            'A3': '=SUM(A1:A2)',
        }

    def test_sheet_qualified_cell(self):
        assert formats.parse_cell_value_pairs("Sheet2!B5 text") == {
            'Sheet2!B5': 'text',
        }

    def test_blank_lines_skipped(self):
        assert formats.parse_cell_value_pairs("\nA1 x\n\nA2 y\n") == {
            'A1': 'x', 'A2': 'y',
        }

    def test_missing_value_raises(self):
        with pytest.raises(ValueError):
            formats.parse_cell_value_pairs("A1")


class TestFormatCellValuePairs:
    def test_basic(self):
        out = formats.format_cell_value_pairs({'A1': 'hello', 'A2': 123})
        # Order is preserved by dict iteration in 3.7+
        assert out == "A1 hello\nA2 123"

    def test_none_becomes_empty(self):
        assert formats.format_cell_value_pairs({'A1': None}) == "A1 "


class TestExpandRangeToCells:
    def test_2x2(self):
        result = formats.expand_range_to_cells(
            "A1:B2", [["a1", "b1"], ["a2", "b2"]]
        )
        assert result == {'A1': 'a1', 'B1': 'b1', 'A2': 'a2', 'B2': 'b2'}

    def test_single_cell_no_colon(self):
        # Single-cell responses come back as 'A1' not 'A1:A1'
        assert formats.expand_range_to_cells("A1", [["x"]]) == {'A1': 'x'}

    def test_single_cell_with_sheet(self):
        assert formats.expand_range_to_cells("Sheet1!A1", [["x"]]) == {
            'Sheet1!A1': 'x',
        }

    def test_sheet_prefix_preserved(self):
        result = formats.expand_range_to_cells(
            "Sheet2!B5:C5", [["a", "b"]]
        )
        assert result == {'Sheet2!B5': 'a', 'Sheet2!C5': 'b'}

    def test_offset_range(self):
        result = formats.expand_range_to_cells("C3:D3", [["x", "y"]])
        assert result == {'C3': 'x', 'D3': 'y'}


class TestDetectFormat:
    def test_json_object(self):
        assert formats.detect_format('{"A1": "x"}') == 'json'

    def test_json_array(self):
        assert formats.detect_format('[1, 2, 3]') == 'json'

    def test_cell_value(self):
        assert formats.detect_format('A1 hello') == 'cell_value'

    def test_leading_whitespace_stripped(self):
        assert formats.detect_format('  \n{"A1": "x"}') == 'json'


class TestParseInput:
    def test_json_dispatch(self):
        assert formats.parse_input('{"A1": "hello"}') == {'A1': 'hello'}

    def test_cell_value_dispatch(self):
        assert formats.parse_input("A1 hello") == {'A1': 'hello'}


class TestReadStdin:
    def test_non_tty_reads(self, monkeypatch):
        fake = io.StringIO("piped\n")
        fake.isatty = lambda: False  # pyright: ignore[reportAttributeAccessIssue]
        monkeypatch.setattr(sys, 'stdin', fake)
        assert formats.read_stdin() == "piped\n"

    def test_tty_returns_empty(self, monkeypatch):
        fake = io.StringIO("")
        fake.isatty = lambda: True  # pyright: ignore[reportAttributeAccessIssue]
        monkeypatch.setattr(sys, 'stdin', fake)
        assert formats.read_stdin() == ""


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
