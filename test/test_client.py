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

    def test_single_cell_shorthand(self):
        """'A1' on its own should work as a 1x1 range."""
        result = a1_to_grid_range('A1', sheet_id=7)
        assert result == {
            'sheetId': 7,
            'startRowIndex': 0, 'endRowIndex': 1,
            'startColumnIndex': 0, 'endColumnIndex': 1,
        }

    def test_whole_column(self):
        """'A:A' should omit row bounds."""
        result = a1_to_grid_range('A:A', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startColumnIndex': 0, 'endColumnIndex': 1,
        }
        assert 'startRowIndex' not in result
        assert 'endRowIndex' not in result

    def test_multi_column(self):
        """'B:D' should span three columns, no row bounds."""
        result = a1_to_grid_range('B:D', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startColumnIndex': 1, 'endColumnIndex': 4,
        }

    def test_whole_row_range(self):
        """'2:5' should span four rows, no column bounds."""
        result = a1_to_grid_range('2:5', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startRowIndex': 1, 'endRowIndex': 5,
        }
        assert 'startColumnIndex' not in result

    def test_single_row(self):
        """'3:3' should be a single row with no column bounds."""
        result = a1_to_grid_range('3:3', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startRowIndex': 2, 'endRowIndex': 3,
        }

    def test_partial_bounds_row_mirrored(self):
        """'A1:C' mirrors the row from the bounded side."""
        result = a1_to_grid_range('A1:C', sheet_id=0)
        # Only the left side had a row, so both row bounds collapse to 1.
        assert result['startRowIndex'] == 0
        assert result['endRowIndex'] == 1
        assert result['startColumnIndex'] == 0
        assert result['endColumnIndex'] == 3

    def test_partial_bounds_column_extended(self):
        """'A:B10' mirrors the row on the left side."""
        result = a1_to_grid_range('A:B10', sheet_id=0)
        assert result['startRowIndex'] == 9
        assert result['endRowIndex'] == 10
        assert result['startColumnIndex'] == 0
        assert result['endColumnIndex'] == 2

    def test_lowercase_accepted(self):
        """Lowercase should be normalized."""
        result = a1_to_grid_range('a1:b2', sheet_id=0)
        assert result == {
            'sheetId': 0,
            'startRowIndex': 0, 'endRowIndex': 2,
            'startColumnIndex': 0, 'endColumnIndex': 2,
        }

    def test_empty_notation_raises(self):
        """Empty string should raise."""
        with pytest.raises(ValueError):
            a1_to_grid_range('', sheet_id=0)


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


class TestListSpreadsheets:
    def _make_client_with_drive(self, response):
        from unittest.mock import MagicMock
        from sheet_client.client import SheetsClient

        mock_drive = MagicMock()
        mock_drive.files.return_value.list.return_value.execute.return_value = response

        client = SheetsClient.__new__(SheetsClient)
        client.drive = mock_drive
        client._execute_with_retry = MagicMock(return_value=response)
        return client, mock_drive

    def test_no_folder_id_query_has_no_parent_filter(self):
        client, mock_drive = self._make_client_with_drive({"files": []})
        client.list_spreadsheets()
        call_kwargs = mock_drive.files.return_value.list.call_args[1]
        assert "in parents" not in call_kwargs['q']

    def test_folder_id_prepends_parent_clause(self):
        files = [{"id": "abc", "name": "Sheet"}]
        client, mock_drive = self._make_client_with_drive({"files": files})
        result = client.list_spreadsheets(folder_id="FOLDER123")
        call_kwargs = mock_drive.files.return_value.list.call_args[1]
        assert "'FOLDER123' in parents" in call_kwargs['q']
        assert result == files


FOLDER_MIME = 'application/vnd.google-apps.folder'


class TestDriveCopyPrimitives:
    def _make_client(self):
        from unittest.mock import MagicMock
        from sheet_client.client import SheetsClient

        mock_drive = MagicMock()
        client = SheetsClient.__new__(SheetsClient)
        client.drive = mock_drive
        client._execute_with_retry = MagicMock()
        return client, mock_drive

    # ------------------------------ get_file_mime ----------------------------

    def test_get_file_mime_returns_mimetype(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {"mimeType": FOLDER_MIME}
        assert client.get_file_mime("FILE1") == FOLDER_MIME
        call_kwargs = mock_drive.files.return_value.get.call_args[1]
        assert call_kwargs["fileId"] == "FILE1"
        assert "mimeType" in call_kwargs["fields"]

    # ------------------------------- copy_file -------------------------------

    def test_copy_file_passes_title_and_parent(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEW", "name": "Doc copy",
            "mimeType": "application/pdf", "parents": ["FOLDER"],
        }
        result = client.copy_file("SRC", new_title="Doc copy",
                                  parent_folder_id="FOLDER")
        body = mock_drive.files.return_value.copy.call_args[1]["body"]
        assert body["name"] == "Doc copy"
        assert body["parents"] == ["FOLDER"]
        assert result["id"] == "NEW"
        assert result["mimeType"] == "application/pdf"
        assert result["parents"] == ["FOLDER"]
        assert "drive.google.com" in result["url"]

    def test_copy_file_omits_empty_body_fields(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEW", "name": "Copy of X",
            "mimeType": "application/pdf", "parents": [],
        }
        client.copy_file("SRC")
        body = mock_drive.files.return_value.copy.call_args[1]["body"]
        assert "name" not in body
        assert "parents" not in body

    # ------------------------------ copy_folder ------------------------------

    def test_copy_folder_rejects_copy_into_self(self):
        client, _ = self._make_client()
        with pytest.raises(ValueError, match="itself"):
            client.copy_folder("F1", parent_folder_id="F1")

    def test_copy_folder_recurses_and_counts(self):
        from unittest.mock import MagicMock
        client, _ = self._make_client()

        # Stub the drive-boundary helpers; exercise the recursion/counting logic.
        client.create_folder = MagicMock(side_effect=[
            {"id": "DST", "name": "Root", "parents": ["P"]},   # top-level copy
            {"id": "DSTSUB", "name": "Sub", "parents": ["DST"]},  # nested copy
        ])
        # Root has: fileA, subfolder(Sub); Sub has: fileB
        client._list_children = MagicMock(side_effect=[
            [{"id": "fa", "name": "A", "mimeType": "text/plain"},
             {"id": "sub", "name": "Sub", "mimeType": FOLDER_MIME}],
            [{"id": "fb", "name": "B", "mimeType": "text/plain"}],
        ])
        client.copy_file = MagicMock(return_value={"id": "x"})

        result = client.copy_folder("ROOT", new_title="Root",
                                    parent_folder_id="P")

        assert result["id"] == "DST"
        assert result["copied_files"] == 2     # A + B
        assert result["copied_folders"] == 1   # Sub
        # Nested folder created under the new top-level folder.
        assert client.create_folder.call_args_list[1].args[1] == "DST"
        # fileB copied into the nested destination folder.
        assert client.copy_file.call_args_list[-1].kwargs["parent_folder_id"] == "DSTSUB"

    # ----------------------------- create_folder -----------------------------

    def test_create_folder_builds_body_and_url(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEWF", "name": "Docs", "parents": ["PARENT"]}
        result = client.create_folder("Docs", parent_folder_id="PARENT")
        body = mock_drive.files.return_value.create.call_args[1]["body"]
        assert body["name"] == "Docs"
        assert body["mimeType"] == FOLDER_MIME
        assert body["parents"] == ["PARENT"]
        assert result["id"] == "NEWF"
        assert "drive.google.com/drive/folders/NEWF" in result["url"]

    def test_create_folder_omits_parents_when_root(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEWF", "name": "Docs", "parents": []}
        client.create_folder("Docs")
        body = mock_drive.files.return_value.create.call_args[1]["body"]
        assert "parents" not in body

    # ------------------------------- list_files ------------------------------

    def test_list_files_root_has_no_parent_filter(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {"files": [{"id": "a"}]}
        result = client.list_files()
        q = mock_drive.files.return_value.list.call_args[1]["q"]
        assert "in parents" not in q
        assert result == [{"id": "a"}]

    def test_list_files_folder_filters_by_parent(self):
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {"files": []}
        client.list_files(folder_id="FOLDER1")
        q = mock_drive.files.return_value.list.call_args[1]["q"]
        assert "'FOLDER1' in parents" in q

    # ----------------------- create() folder placement -----------------------

    def test_create_with_parent_moves_into_folder(self):
        from unittest.mock import MagicMock
        client, _ = self._make_client()
        # spreadsheets.create returns the new SID; mock the Sheets path + helpers.
        client.spreadsheets = MagicMock()
        client._execute_with_retry.return_value = {
            "spreadsheetId": "NEWSID",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/NEWSID",
        }
        client.get_parents = MagicMock(return_value=["ROOT"])
        client.update_parents = MagicMock(return_value={"id": "NEWSID"})
        result = client.create("Budget", parent_folder_id="FOLDER9")
        assert result["spreadsheetId"] == "NEWSID"
        client.update_parents.assert_called_once_with(
            "NEWSID", add=["FOLDER9"], remove=["ROOT"])

    def test_create_without_parent_does_not_move(self):
        from unittest.mock import MagicMock
        client, _ = self._make_client()
        client.spreadsheets = MagicMock()
        client._execute_with_retry.return_value = {
            "spreadsheetId": "NEWSID",
            "spreadsheetUrl": "u",
        }
        client.update_parents = MagicMock()
        client.create("Budget")
        client.update_parents.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
