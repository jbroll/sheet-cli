"""Main Google Sheets API client."""

import time
from enum import IntFlag
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_credentials
from .exceptions import SheetsAPIError, RateLimitError, ServerError


class CellData(IntFlag):
    """Flags for specifying what data to fetch when reading."""
    VALUE = 1      # Cell values (numbers, strings, booleans)
    FORMULA = 2    # Formulas (=SUM(A:A))
    FORMAT = 4     # Formatting (colors, fonts, borders, number formats)
    NOTE = 8       # Cell notes/comments


class SheetsClient:
    """Minimal wrapper for Google Sheets REST API v4.

    Provides four core operations:
    1. read() - Read cell data
    2. write() - Write cell data
    3. meta_read() - Read spreadsheet metadata/structure
    4. meta_write() - Modify spreadsheet metadata/structure

    Args:
        spreadsheet_id: The ID of the Google Spreadsheet
        credentials_path: Path to OAuth client credentials JSON
                         (defaults to ~/.sheet-cli/credentials.json)
        token_path: Path to cached token file
                   (defaults to ~/.sheet-cli/token.pickle)
    """

    def __init__(self, credentials_path: Optional[str] = None,
                 token_path: Optional[str] = None):
        """Initialize the Sheets client with OAuth credentials.

        Args:
            credentials_path: Path to OAuth client credentials JSON
                             (defaults to ~/.sheet-cli/credentials.json)
            token_path: Path to cached token file
                       (defaults to ~/.sheet-cli/token.pickle)
        """
        creds = get_credentials(credentials_path, token_path)
        self.service = build('sheets', 'v4', credentials=creds)
        self.spreadsheets = self.service.spreadsheets()
        self.drive = build('drive', 'v3', credentials=creds)

    def _get_spreadsheet_id(self, spreadsheet_id: str) -> str:
        """Validate and return spreadsheet ID.

        Args:
            spreadsheet_id: Spreadsheet ID (required)

        Returns:
            Spreadsheet ID to use

        Raises:
            ValueError: If spreadsheet_id is None or empty
        """
        if not spreadsheet_id:
            raise ValueError(
                "spreadsheet_id is required. Pass spreadsheet_id parameter to method."
            )
        return spreadsheet_id

    def _execute_with_retry(self, request, max_retries: int = 3) -> Any:
        """Execute API request with exponential backoff for rate limits and server errors.

        Args:
            request: Google API request object
            max_retries: Maximum number of retry attempts

        Returns:
            API response

        Raises:
            RateLimitError: If rate limit exceeded after retries
            ServerError: If server error persists after retries
            SheetsAPIError: For other API errors
        """
        for attempt in range(max_retries):
            try:
                return request.execute()
            except HttpError as e:
                status_code = e.resp.status

                # Rate limit (429) - retry with backoff
                if status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt)
                        time.sleep(wait_time)
                        continue
                    raise RateLimitError(
                        f"Rate limit exceeded after {max_retries} retries",
                        status_code=status_code,
                        response=e.error_details if hasattr(e, 'error_details') else None
                    )

                # Server errors (500, 503) - retry with backoff
                elif status_code in (500, 503):
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt)
                        time.sleep(wait_time)
                        continue
                    raise ServerError(
                        f"Server error {status_code} after {max_retries} retries",
                        status_code=status_code,
                        response=e.error_details if hasattr(e, 'error_details') else None
                    )

                # Other errors - raise immediately
                else:
                    raise SheetsAPIError(
                        f"API error {status_code}: {str(e)}",
                        status_code=status_code,
                        response=e.error_details if hasattr(e, 'error_details') else None
                    )

        raise SheetsAPIError("Unexpected error in retry logic")

    def read(self, spreadsheet_id: str, ranges: List[str],
             types: int = CellData.VALUE) -> dict:
        """Read cells from specified ranges.

        Args:
            spreadsheet_id: Spreadsheet ID (required)
            ranges: List of A1 notation ranges
                ['Sheet1!A1:C10']
                ['Sheet1!A1:C10', 'Sheet2!B2:D5']
                ['Sheet1!A:A']  # Entire column
                ['Sheet1!1:1']  # Entire row

            types: Bitmask of what to fetch (default: CellData.VALUE)
                CellData.VALUE    - Values only (fastest)
                CellData.FORMULA  - Show formulas as strings
                CellData.FORMAT   - Cell formatting
                CellData.NOTE     - Cell notes/comments

                Combine with | operator:
                    CellData.VALUE | CellData.FORMULA
                    CellData.VALUE | CellData.FORMULA | CellData.FORMAT

        Returns:
            Raw API response dict with requested cell data.

            Single range response:
            {
                'spreadsheetId': '...',
                'range': 'Sheet1!A1:C10',
                'values': [[1, 2, 3], [4, 5, 6], ...]
            }

            Multiple ranges response:
            {
                'spreadsheetId': '...',
                'valueRanges': [
                    {'range': 'Sheet1!A1:C10', 'values': [...]},
                    {'range': 'Sheet2!B2:D5', 'values': [...]}
                ]
            }

            With FORMAT or NOTE, includes additional cell properties.

        Examples:
            # Read values only (fastest)
            data = client.read('spreadsheet-id', ['Sheet1!A1:C10'])

            # Read values and formulas
            data = client.read(
                'spreadsheet-id',
                ['Sheet1!A1:C10'],
                types=CellData.VALUE | CellData.FORMULA
            )

            # Read everything
            data = client.read(
                'spreadsheet-id',
                ['Sheet1!A1:C10'],
                types=CellData.VALUE | CellData.FORMULA | CellData.FORMAT | CellData.NOTE
            )

            # Read multiple ranges
            data = client.read(
                'spreadsheet-id',
                ['Sheet1!A1:C10', 'Sheet2!B2:D5', 'Summary!A1']
            )
        """
        # Get spreadsheet ID
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)

        # Check if we need grid data (for FORMAT or NOTE)
        need_grid_data = bool(types & (CellData.FORMAT | CellData.NOTE))

        if need_grid_data:
            # Use spreadsheets.get for full cell data
            request = self.spreadsheets.get(
                spreadsheetId=sheet_id,
                includeGridData=True,
                ranges=ranges
            )
            return self._execute_with_retry(request)
        else:
            # Use values API for faster value-only reads
            value_render = 'FORMULA' if (types & CellData.FORMULA) else 'FORMATTED_VALUE'

            if len(ranges) == 1:
                # Single range - use values.get
                request = self.spreadsheets.values().get(
                    spreadsheetId=sheet_id,
                    range=ranges[0],
                    valueRenderOption=value_render
                )
            else:
                # Multiple ranges - use values.batchGet
                request = self.spreadsheets.values().batchGet(
                    spreadsheetId=sheet_id,
                    ranges=ranges,
                    valueRenderOption=value_render
                )

            return self._execute_with_retry(request)

    def write(self, spreadsheet_id: str, data: List[dict]) -> dict:
        """Write cell values in a single batched call.

        Args:
            spreadsheet_id: Spreadsheet ID (required)
            data: List of write operations, each with 'range' (A1 notation)
                and 'values' (2D array). Formulas start with '='.

                [
                    {'range': 'Sheet1!A1', 'values': [[1, 2, 3], [4, 5, 6]]},
                    {'range': 'Sheet2!B5', 'values': [['text', '=SUM(A:A)']]},
                ]

        Returns:
            Raw API response with update results:
            {
                'spreadsheetId': '...',
                'totalUpdatedRows': 10,
                'totalUpdatedColumns': 5,
                'totalUpdatedCells': 50,
                'responses': [...]
            }

        Notes:
            - Uses valueInputOption=USER_ENTERED (formulas and dates are parsed).
            - To clear values, use clear(). To write formatting or notes, use
              meta_write() with repeatCell / updateCells requests.

        Examples:
            # Write values
            client.write('spreadsheet-id', [{
                'range': 'Sheet1!A1',
                'values': [[1, 2, 3], [4, 5, 6]]
            }])

            # Write formulas
            client.write('spreadsheet-id', [{
                'range': 'Sheet1!D1',
                'values': [['=SUM(A1:C1)'], ['=SUM(A2:C2)']]
            }])

            # Batch write multiple ranges
            client.write('spreadsheet-id', [
                {'range': 'Sheet1!A1', 'values': [[1, 2, 3]]},
                {'range': 'Sheet2!B5', 'values': [[4, 5, 6]]},
                {'range': 'Sheet3!C10', 'values': [[7, 8, 9]]}
            ])
        """
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)

        value_data = [{'range': d['range'], 'values': d['values']} for d in data]
        body = {
            'valueInputOption': 'USER_ENTERED',
            'data': value_data,
        }
        request = self.spreadsheets.values().batchUpdate(
            spreadsheetId=sheet_id,
            body=body,
        )
        return self._execute_with_retry(request)

    def clear(self, spreadsheet_id: str, ranges: List[str]) -> dict:
        """Clear cell values in one or more ranges.

        Uses values.batchClear — removes values and formulas but preserves
        formatting, notes, merges, and other cell metadata. To clear those,
        use meta_write() with updateCells.

        Args:
            spreadsheet_id: Spreadsheet ID (required)
            ranges: List of A1 notation ranges to clear

        Returns:
            Raw API response:
            {
                'spreadsheetId': '...',
                'clearedRanges': ['Sheet1!A1:B10', ...]
            }
        """
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)
        request = self.spreadsheets.values().batchClear(
            spreadsheetId=sheet_id,
            body={'ranges': ranges},
        )
        return self._execute_with_retry(request)

    def meta_read(self, spreadsheet_id: str) -> dict:
        """Read spreadsheet metadata and structure.

        Read-only view of spreadsheet structure without cell data.

        Args:
            spreadsheet_id: Spreadsheet ID (required)

        Returns:
            Raw API response dict with:
            {
                'spreadsheetId': '...',
                'properties': {
                    'title': 'Spreadsheet Name',
                    'locale': 'en_US',
                    'timeZone': 'America/New_York'
                },
                'sheets': [
                    {
                        'properties': {
                            'sheetId': 0,
                            'title': 'Sheet1',
                            'index': 0,
                            'gridProperties': {
                                'rowCount': 1000,
                                'columnCount': 26,
                                'frozenRowCount': 0,
                                'frozenColumnCount': 0
                            }
                        }
                    }
                ],
                'namedRanges': [...],
                'conditionalFormats': [...]
            }

        Examples:
            # Get all sheets
            meta = client.meta_read('spreadsheet-id')
            for sheet in meta['sheets']:
                print(f"Sheet: {sheet['properties']['title']}")
                print(f"  ID: {sheet['properties']['sheetId']}")

            # Find sheet ID by name
            meta = client.meta_read('spreadsheet-id')
            sheet_id = next(
                s['properties']['sheetId']
                for s in meta['sheets']
                if s['properties']['title'] == 'Sales'
            )

            # List named ranges
            meta = client.meta_read('spreadsheet-id')
            for nr in meta.get('namedRanges', []):
                print(f"{nr['name']}: {nr['range']}")
        """
        # Get spreadsheet ID
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)

        request = self.spreadsheets.get(
            spreadsheetId=sheet_id,
            includeGridData=False
        )
        return self._execute_with_retry(request)

    def meta_write(self, spreadsheet_id: str, requests: List[dict]) -> dict:
        """Write/modify spreadsheet metadata and structure.

        Direct access to spreadsheets.batchUpdate API.
        Performs structural operations (not cell value writes).

        Args:
            spreadsheet_id: Spreadsheet ID (required)
            requests: List of request dicts (max 500 per call)

        Returns:
            {
                'spreadsheetId': '...',
                'replies': [...]  # Responses for each request
            }

        Common Request Types:

        Sheet Operations:
            addSheet - Create new sheet
            deleteSheet - Delete sheet
            updateSheetProperties - Modify sheet (title, colors, grid size)

        Dimension Operations:
            insertDimension - Insert rows/columns
            deleteDimension - Delete rows/columns
            updateDimensionProperties - Resize, hide/show, freeze
            autoResizeDimensions - Auto-fit column widths

        Cell Structure:
            mergeCells - Merge cell range
            unmergeCells - Unmerge cells

        Formatting:
            repeatCell - Apply format to range
            updateCells - Write values with format

        Named Ranges:
            addNamedRange - Create named range
            deleteNamedRange - Delete named range

        Conditional Formatting:
            addConditionalFormatRule - Add formatting rule
            deleteConditionalFormatRule - Delete rule

        Protection:
            addProtectedRange - Protect cells
            deleteProtectedRange - Unprotect cells

        Other:
            findReplace - Find and replace across sheet
            sortRange - Sort data
            copyPaste - Copy range
            cutPaste - Move range

        See: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request

        Examples:
            # Add new sheet
            client.meta_write('spreadsheet-id', [{
                'addSheet': {
                    'properties': {
                        'title': 'Sales Data',
                        'gridProperties': {
                            'rowCount': 100,
                            'columnCount': 10
                        }
                    }
                }
            }])

            # Freeze top row
            sheet_id = 0  # From meta_read()
            client.meta_write('spreadsheet-id', [{
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'gridProperties': {
                            'frozenRowCount': 1
                        }
                    },
                    'fields': 'gridProperties.frozenRowCount'
                }
            }])

            # Format header row
            client.meta_write('spreadsheet-id', [{
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                            'textFormat': {'bold': True}
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                }
            }])

            # Batch multiple operations
            client.meta_write('spreadsheet-id', [
                {'addSheet': {'properties': {'title': 'Dashboard'}}},
                {'updateSheetProperties': {...}},
                {'autoResizeDimensions': {...}}
            ])
        """
        # Get spreadsheet ID
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)

        body = {'requests': requests}
        request = self.spreadsheets.batchUpdate(
            spreadsheetId=sheet_id,
            body=body
        )
        return self._execute_with_retry(request)

    def list_spreadsheets(self, include_shared_drives: bool = False) -> List[dict]:
        """List spreadsheets visible to the authenticated user.

        Args:
            include_shared_drives: If True, also search Shared Drives
                                   (organizational/team drives). Defaults to False,
                                   which returns files from My Drive and Shared With Me.

        Returns:
            List of file metadata dicts (all pages merged):
            [
                {
                    'id': '...',           # Spreadsheet ID (use with other commands)
                    'name': '...',         # File name
                    'modifiedTime': '...', # ISO 8601 timestamp
                    'owners': [{'displayName': '...', 'emailAddress': '...'}],
                    'shared': True/False
                },
                ...
            ]
        """
        files = []
        page_token = None
        query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"

        while True:
            kwargs = {
                'q': query,
                'fields': 'nextPageToken, files(id,name,modifiedTime,owners,shared)',
                'pageSize': 1000,
            }
            if page_token:
                kwargs['pageToken'] = page_token
            if include_shared_drives:
                kwargs['includeItemsFromAllDrives'] = True
                kwargs['supportsAllDrives'] = True

            request = self.drive.files().list(**kwargs)
            response = self._execute_with_retry(request)
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break

        return files

    def create(self, title: str, sheets: Optional[List[dict]] = None) -> dict:
        """Create a new spreadsheet.

        Args:
            title: Title for the new spreadsheet
            sheets: Optional list of sheet properties dicts.
                    If not provided, creates a single default sheet named 'Sheet1'.

                    Example:
                    [
                        {
                            'properties': {
                                'title': 'Sales Data',
                                'gridProperties': {
                                    'rowCount': 100,
                                    'columnCount': 10
                                }
                            }
                        }
                    ]

        Returns:
            Raw API response dict with:
            {
                'spreadsheetId': '...',
                'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/...',
                'properties': {
                    'title': 'Spreadsheet Name',
                    'locale': 'en_US',
                    'timeZone': 'America/New_York'
                },
                'sheets': [
                    {
                        'properties': {
                            'sheetId': 0,
                            'title': 'Sheet1',
                            'index': 0,
                            'gridProperties': {
                                'rowCount': 1000,
                                'columnCount': 26
                            }
                        }
                    }
                ]
            }

        Examples:
            # Create spreadsheet with default sheet
            result = client.create('My Spreadsheet')
            spreadsheet_id = result['spreadsheetId']
            print(f"Created: {result['spreadsheetUrl']}")

            # Create with custom sheet properties
            result = client.create(
                'Sales Report',
                sheets=[{
                    'properties': {
                        'title': 'Q1 Sales',
                        'gridProperties': {
                            'rowCount': 100,
                            'columnCount': 20
                        }
                    }
                }]
            )

            # Create with multiple sheets
            result = client.create(
                'Multi-Sheet Report',
                sheets=[
                    {'properties': {'title': 'Sales'}},
                    {'properties': {'title': 'Expenses'}},
                    {'properties': {'title': 'Summary'}}
                ]
            )
        """
        body: Dict[str, Any] = {
            'properties': {
                'title': title
            }
        }

        if sheets:
            body['sheets'] = sheets

        request = self.spreadsheets.create(body=body)
        return self._execute_with_retry(request)

    def copy_sheet_to(self, source_spreadsheet_id: str, source_sheet_id: int,
                      destination_spreadsheet_id: str) -> dict:
        """Copy a sheet from one spreadsheet to another using sheets.copyTo.

        Server-side operation — data stays within Google's infrastructure.

        Args:
            source_spreadsheet_id: Spreadsheet ID containing the source sheet
            source_sheet_id: Numeric sheet ID (not title) of the source sheet
            destination_spreadsheet_id: Target spreadsheet ID

        Returns:
            Raw API response with the new sheet's properties:
            {
                'sheetId': ...,
                'title': 'Copy of ...',
                'index': ...,
                'gridProperties': {...}
            }
        """
        request = self.spreadsheets.sheets().copyTo(
            spreadsheetId=source_spreadsheet_id,
            sheetId=source_sheet_id,
            body={'destinationSpreadsheetId': destination_spreadsheet_id},
        )
        return self._execute_with_retry(request)

    def delete_spreadsheet(self, spreadsheet_id: str) -> None:
        """Delete a spreadsheet via the Drive API (moves it to trash).

        Args:
            spreadsheet_id: Spreadsheet ID to delete
        """
        sheet_id = self._get_spreadsheet_id(spreadsheet_id)
        request = self.drive.files().delete(fileId=sheet_id)
        self._execute_with_retry(request)
