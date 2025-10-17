"""Tests for refactored SheetsClient with optional spreadsheet_id."""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient, CellData


class TestSpreadsheetIdHandling:
    """Test spreadsheet_id parameter handling."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_init_without_spreadsheet_id(self, mock_build, mock_creds):
        """Test initialization (no spreadsheet_id in constructor)."""
        mock_service = Mock()
        mock_build.return_value = mock_service

        client = SheetsClient()

        assert client is not None
        mock_creds.assert_called_once()

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_get_spreadsheet_id_with_parameter(self, mock_build, mock_creds):
        """Test getting spreadsheet_id from parameter."""
        mock_service = Mock()
        mock_build.return_value = mock_service

        client = SheetsClient()

        result = client._get_spreadsheet_id('test-sheet-123')
        assert result == 'test-sheet-123'

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_get_spreadsheet_id_none_raises_error(self, mock_build, mock_creds):
        """Test error when spreadsheet_id is None."""
        mock_service = Mock()
        mock_build.return_value = mock_service

        client = SheetsClient()

        with pytest.raises(ValueError, match="spreadsheet_id is required"):
            client._get_spreadsheet_id(None)

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_get_spreadsheet_id_empty_string_raises_error(self, mock_build, mock_creds):
        """Test error when spreadsheet_id is empty string."""
        mock_service = Mock()
        mock_build.return_value = mock_service

        client = SheetsClient()

        with pytest.raises(ValueError, match="spreadsheet_id is required"):
            client._get_spreadsheet_id('')


class TestReadMethodSpreadsheetId:
    """Test read() method with spreadsheet_id parameter."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_read_with_spreadsheet_id(self, mock_build, mock_creds):
        """Test read() with spreadsheet_id parameter."""
        mock_service = Mock()
        mock_spreadsheets = Mock()
        mock_values = Mock()
        mock_service.spreadsheets.return_value = mock_spreadsheets
        mock_spreadsheets.values.return_value = mock_values

        mock_request = Mock()
        mock_values.get.return_value = mock_request
        mock_request.execute.return_value = {'values': [['test']]}

        mock_build.return_value = mock_service

        client = SheetsClient()
        result = client.read('test-sheet', ['A1'])

        # Verify it used the provided spreadsheet_id
        mock_values.get.assert_called_once()
        call_kwargs = mock_values.get.call_args[1]
        assert call_kwargs['spreadsheetId'] == 'test-sheet'

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_read_fails_with_none_spreadsheet_id(self, mock_build, mock_creds):
        """Test read() raises error when spreadsheet_id is None."""
        mock_service = Mock()
        mock_build.return_value = mock_service

        client = SheetsClient()

        with pytest.raises(ValueError, match="spreadsheet_id is required"):
            client.read(None, ['A1'])


class TestWriteMethodSpreadsheetId:
    """Test write() method with spreadsheet_id parameter."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_write_with_spreadsheet_id(self, mock_build, mock_creds):
        """Test write() with spreadsheet_id parameter."""
        mock_service = Mock()
        mock_spreadsheets = Mock()
        mock_values = Mock()
        mock_service.spreadsheets.return_value = mock_spreadsheets
        mock_spreadsheets.values.return_value = mock_values

        mock_request = Mock()
        mock_values.batchUpdate.return_value = mock_request
        mock_request.execute.return_value = {'totalUpdatedCells': 1}

        mock_build.return_value = mock_service

        client = SheetsClient()
        result = client.write('test-sheet', [{'range': 'A1', 'values': [[1]]}])

        # Verify it used the provided spreadsheet_id
        mock_values.batchUpdate.assert_called_once()
        call_kwargs = mock_values.batchUpdate.call_args[1]
        assert call_kwargs['spreadsheetId'] == 'test-sheet'


class TestMetaReadMethod:
    """Test meta_read() method with spreadsheet_id parameter."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_meta_read_with_spreadsheet_id(self, mock_build, mock_creds):
        """Test meta_read() with spreadsheet_id parameter."""
        mock_service = Mock()
        mock_spreadsheets = Mock()
        mock_service.spreadsheets.return_value = mock_spreadsheets

        mock_request = Mock()
        mock_spreadsheets.get.return_value = mock_request
        mock_request.execute.return_value = {'spreadsheetId': 'test-sheet'}

        mock_build.return_value = mock_service

        client = SheetsClient()
        result = client.meta_read('test-sheet')

        # Verify it used the provided spreadsheet_id
        mock_spreadsheets.get.assert_called_once()
        call_kwargs = mock_spreadsheets.get.call_args[1]
        assert call_kwargs['spreadsheetId'] == 'test-sheet'


class TestMetaWriteMethod:
    """Test meta_write() method with spreadsheet_id parameter."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_meta_write_with_spreadsheet_id(self, mock_build, mock_creds):
        """Test meta_write() with spreadsheet_id parameter."""
        mock_service = Mock()
        mock_spreadsheets = Mock()
        mock_service.spreadsheets.return_value = mock_spreadsheets

        mock_request = Mock()
        mock_spreadsheets.batchUpdate.return_value = mock_request
        mock_request.execute.return_value = {'spreadsheetId': 'test-sheet'}

        mock_build.return_value = mock_service

        client = SheetsClient()
        result = client.meta_write('test-sheet', [{'addSheet': {'properties': {'title': 'Test'}}}])

        # Verify it used the provided spreadsheet_id
        mock_spreadsheets.batchUpdate.assert_called_once()
        call_kwargs = mock_spreadsheets.batchUpdate.call_args[1]
        assert call_kwargs['spreadsheetId'] == 'test-sheet'


class TestMCPPattern:
    """Test MCP usage pattern - single client, multiple spreadsheets."""

    @patch('sheet_client.client.get_credentials')
    @patch('sheet_client.client.build')
    def test_single_client_multiple_sheets(self, mock_build, mock_creds):
        """Test using one client for multiple spreadsheets."""
        mock_service = Mock()
        mock_spreadsheets = Mock()
        mock_values = Mock()
        mock_service.spreadsheets.return_value = mock_spreadsheets
        mock_spreadsheets.values.return_value = mock_values

        mock_request = Mock()
        mock_values.get.return_value = mock_request
        mock_request.execute.return_value = {'values': [['test']]}

        mock_build.return_value = mock_service

        # MCP pattern: one client, many sheets
        client = SheetsClient()

        # First spreadsheet
        result1 = client.read('sheet-1', ['A1'])
        # Second spreadsheet
        result2 = client.read('sheet-2', ['B1'])

        # Both calls should work
        assert mock_values.get.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
