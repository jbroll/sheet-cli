"""Integration tests for SheetsClient with real Google Sheets API.

These tests require:
1. ~/.sheet-cli/credentials.json
2. A real Google Spreadsheet
3. OAuth authentication (browser will open on first run)

Set SHEETS_TEST_SPREADSHEET_ID environment variable to run these tests.

Usage:
    export SHEETS_TEST_SPREADSHEET_ID="your-spreadsheet-id-here"
    pytest test_integration.py -v -s
"""

import os
import sys
import pytest
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient, CellData


# Skip all tests if SHEETS_TEST_SPREADSHEET_ID not set
pytestmark = pytest.mark.skipif(
    not os.environ.get('SHEETS_TEST_SPREADSHEET_ID'),
    reason="Set SHEETS_TEST_SPREADSHEET_ID environment variable to run integration tests"
)


@pytest.fixture
def spreadsheet_id():
    """Get test spreadsheet ID from environment."""
    return os.environ.get('SHEETS_TEST_SPREADSHEET_ID')


@pytest.fixture
def client():
    """Create SheetsClient (no default spreadsheet_id)."""
    return SheetsClient()


class TestOAuthFlow:
    """Test OAuth authentication flow."""

    def test_oauth_flow_creates_token(self, client):
        """Test that OAuth flow works and creates token file."""
        # Simply creating the client should trigger OAuth if needed
        assert client is not None
        assert client.service is not None

        # Check if token was created in ~/.sheet-cli/
        token_path = os.path.expanduser('~/.sheet-cli/token.pickle')
        assert os.path.exists(token_path), \
            "~/.sheet-cli/token.pickle should be created after OAuth flow"

    def test_cached_token_reused(self, client):
        """Test that cached token is reused on subsequent runs."""
        # This should not trigger browser if token exists
        client2 = SheetsClient()
        assert client2 is not None


class TestBasicOperations:
    """Test basic read/write operations."""

    def test_metadata(self, client, spreadsheet_id):
        """Test meta_read() with spreadsheet_id."""
        result = client.meta_read(spreadsheet_id)

        assert 'spreadsheetId' in result
        assert result['spreadsheetId'] == spreadsheet_id
        assert 'properties' in result
        assert 'sheets' in result
        assert len(result['sheets']) > 0

    def test_read(self, client, spreadsheet_id):
        """Test read() with spreadsheet_id."""
        result = client.read(spreadsheet_id, ['A1:A1'])

        assert 'spreadsheetId' in result or 'range' in result
        # values may be empty if cell is empty

    def test_write_read_roundtrip(self, client, spreadsheet_id):
        """Test writing and reading back a value."""
        # Generate unique test value with timestamp
        test_value = f"Test_{int(time.time())}"

        # Write to cell
        write_result = client.write(
            spreadsheet_id,
            [{'range': 'Sheet1!Z1', 'values': [[test_value]]}]
        )

        assert 'totalUpdatedCells' in write_result
        assert write_result['totalUpdatedCells'] >= 1

        # Read it back
        read_result = client.read(spreadsheet_id, ['Sheet1!Z1'])

        assert 'values' in read_result
        assert read_result['values'][0][0] == test_value

    def test_formula_write_read(self, client, spreadsheet_id):
        """Test writing and reading a formula."""
        # Write formula
        write_result = client.write(
            spreadsheet_id,
            [{'range': 'Sheet1!Z2', 'values': [['=1+1']]}]
        )

        assert write_result['totalUpdatedCells'] >= 1

        # Read as value (should show calculated result)
        value_result = client.read(
            spreadsheet_id,
            ['Sheet1!Z2'],
            types=CellData.VALUE
        )

        assert 'values' in value_result
        assert value_result['values'][0][0] == 2

        # Read as formula (should show formula string)
        formula_result = client.read(
            spreadsheet_id,
            ['Sheet1!Z2'],
            types=CellData.FORMULA
        )

        assert 'values' in formula_result
        assert formula_result['values'][0][0] == '=1+1'


class TestMultipleSpreadsheets:
    """Test working with multiple spreadsheets."""

    def test_single_client_multiple_sheets(self, client, spreadsheet_id):
        """Test using single client with multiple spreadsheets via parameters."""
        # This test shows the MCP use case: one client, many spreadsheets

        # Read from spreadsheet
        result1 = client.meta_read(spreadsheet_id)
        assert result1['spreadsheetId'] == spreadsheet_id

        # Could read from another spreadsheet if we had another ID
        # result2 = client.meta_read(another_spreadsheet_id)
        # This demonstrates the pattern we need for MCP


class TestStructureOperations:
    """Test structure modification operations."""

    def test_get_sheet_id(self, client, spreadsheet_id):
        """Test getting sheet ID from meta_read (needed for structure ops)."""
        meta = client.meta_read(spreadsheet_id)

        assert 'sheets' in meta
        assert len(meta['sheets']) > 0

        first_sheet = meta['sheets'][0]
        assert 'properties' in first_sheet
        assert 'sheetId' in first_sheet['properties']
        assert 'title' in first_sheet['properties']

        sheet_id = first_sheet['properties']['sheetId']
        sheet_title = first_sheet['properties']['title']

        print(f"\nFirst sheet: '{sheet_title}' (ID: {sheet_id})")


class TestErrorHandling:
    """Test error handling."""

    def test_no_spreadsheet_id_raises_error(self, client):
        """Test that missing spreadsheet_id raises clear error."""
        with pytest.raises(ValueError, match="spreadsheet_id is required"):
            client.read(None, ['A1'])

    def test_invalid_spreadsheet_id(self, client):
        """Test handling of invalid spreadsheet ID."""
        from sheet_client import SheetsAPIError

        with pytest.raises(SheetsAPIError):
            client.read('invalid-id-12345', ['A1'])


if __name__ == '__main__':
    print("\nIntegration Tests for SheetsClient")
    print("=" * 50)
    print("\nThese tests require:")
    print("1. ~/.sheet-cli/credentials.json")
    print("2. Set SHEETS_TEST_SPREADSHEET_ID environment variable")
    print("3. OAuth browser flow on first run\n")

    if not os.environ.get('SHEETS_TEST_SPREADSHEET_ID'):
        print("ERROR: SHEETS_TEST_SPREADSHEET_ID not set!")
        print("\nUsage:")
        print("  export SHEETS_TEST_SPREADSHEET_ID='your-spreadsheet-id'")
        print("  python test_integration.py\n")
        sys.exit(1)

    pytest.main([__file__, '-v', '-s'])
