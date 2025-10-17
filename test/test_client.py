"""Unit tests for Google Sheets CLI."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from sheet_client.utils import column_to_index, index_to_column, a1_to_grid_range


class TestColumnConversion:
    """Test column letter to index conversion."""

    def test_column_to_index_single_letter(self):
        """Test single letter columns."""
        assert column_to_index('A') == 0
        assert column_to_index('B') == 1
        assert column_to_index('Z') == 25

    def test_column_to_index_double_letter(self):
        """Test double letter columns."""
        assert column_to_index('AA') == 26
        assert column_to_index('AB') == 27
        assert column_to_index('AZ') == 51
        assert column_to_index('BA') == 52

    def test_column_to_index_triple_letter(self):
        """Test triple letter columns."""
        assert column_to_index('AAA') == 702

    def test_column_to_index_case_insensitive(self):
        """Test that lowercase is handled."""
        assert column_to_index('a') == 0
        assert column_to_index('aa') == 26

    def test_index_to_column_single_digit(self):
        """Test single digit indices."""
        assert index_to_column(0) == 'A'
        assert index_to_column(1) == 'B'
        assert index_to_column(25) == 'Z'

    def test_index_to_column_double_digit(self):
        """Test double digit indices."""
        assert index_to_column(26) == 'AA'
        assert index_to_column(27) == 'AB'
        assert index_to_column(51) == 'AZ'
        assert index_to_column(52) == 'BA'

    def test_index_to_column_triple_digit(self):
        """Test triple digit indices."""
        assert index_to_column(702) == 'AAA'

    def test_round_trip_conversion(self):
        """Test that conversion works both ways."""
        for i in range(0, 1000):
            col = index_to_column(i)
            assert column_to_index(col) == i


class TestA1ToGridRange:
    """Test A1 notation to GridRange conversion."""

    def test_basic_range(self):
        """Test basic range conversion."""
        result = a1_to_grid_range('A1:C10', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startRowIndex': 0,
            'endRowIndex': 10,
            'startColumnIndex': 0,
            'endColumnIndex': 3
        }

    def test_single_cell(self):
        """Test single cell range."""
        result = a1_to_grid_range('B5:B5', sheet_id=1)
        assert result == {
            'sheetId': 1,
            'startRowIndex': 4,
            'endRowIndex': 5,
            'startColumnIndex': 1,
            'endColumnIndex': 2
        }

    def test_with_sheet_name(self):
        """Test range with sheet name (should be ignored)."""
        result = a1_to_grid_range('Sheet1!A1:C10', sheet_id=5)
        assert result == {
            'sheetId': 5,
            'startRowIndex': 0,
            'endRowIndex': 10,
            'startColumnIndex': 0,
            'endColumnIndex': 3
        }

    def test_large_columns(self):
        """Test with large column letters."""
        result = a1_to_grid_range('AA1:AB10', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startRowIndex': 0,
            'endRowIndex': 10,
            'startColumnIndex': 26,
            'endColumnIndex': 28
        }

    def test_invalid_notation(self):
        """Test that invalid notation raises error."""
        with pytest.raises(ValueError):
            a1_to_grid_range('InvalidNotation', sheet_id=0)

    def test_exclusive_end_indices(self):
        """Test that end indices are exclusive (Python-like slicing)."""
        result = a1_to_grid_range('A1:A1', sheet_id=0)
        # First row only: startRowIndex=0, endRowIndex=1
        assert result['startRowIndex'] == 0
        assert result['endRowIndex'] == 1
        # First column only: startColumnIndex=0, endColumnIndex=1
        assert result['startColumnIndex'] == 0
        assert result['endColumnIndex'] == 1


class TestExceptions:
    """Test custom exceptions."""

    def test_sheets_api_error_with_status(self):
        """Test SheetsAPIError with status code."""
        from sheet_client.exceptions import SheetsAPIError

        error = SheetsAPIError("Test error", status_code=400, response={'error': 'details'})
        assert str(error) == "Test error"
        assert error.status_code == 400
        assert error.response == {'error': 'details'}

    def test_authentication_error(self):
        """Test AuthenticationError."""
        from sheet_client.exceptions import AuthenticationError

        error = AuthenticationError("Auth failed")
        assert str(error) == "Auth failed"

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        from sheet_client.exceptions import RateLimitError

        error = RateLimitError("Rate limit exceeded", status_code=429)
        assert str(error) == "Rate limit exceeded"
        assert error.status_code == 429


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
