"""Main Google Sheets API client."""

import time
from enum import IntFlag
from typing import Any, Dict, List

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
    1. read() - Read cells with type flags
    2. write() - Write values/format/notes
    3. metadata() - Get spreadsheet structure
    4. structure() - Batch operations

    Args:
        spreadsheet_id: The ID of the Google Spreadsheet
        credentials_path: Path to OAuth client credentials JSON (default: 'credentials.json')
        token_path: Path to cached token file (default: 'token.pickle')
    """

    def __init__(self, spreadsheet_id: str,
                 credentials_path: str = 'credentials.json',
                 token_path: str = 'token.pickle'):
        """Initialize the Sheets client with OAuth credentials."""
        self.spreadsheet_id = spreadsheet_id
        creds = get_credentials(credentials_path, token_path)
        self.service = build('sheets', 'v4', credentials=creds)
        self.spreadsheets = self.service.spreadsheets()

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

    def read(self, ranges: List[str], types: int = CellData.VALUE) -> dict:
        """Read cells from specified ranges.

        Args:
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
            data = client.read(['Sheet1!A1:C10'])

            # Read values and formulas
            data = client.read(
                ['Sheet1!A1:C10'],
                types=CellData.VALUE | CellData.FORMULA
            )

            # Read everything
            data = client.read(
                ['Sheet1!A1:C10'],
                types=CellData.VALUE | CellData.FORMULA | CellData.FORMAT | CellData.NOTE
            )

            # Read multiple ranges
            data = client.read([
                'Sheet1!A1:C10',
                'Sheet2!B2:D5',
                'Summary!A1'
            ])
        """
        # Check if we need grid data (for FORMAT or NOTE)
        need_grid_data = bool(types & (CellData.FORMAT | CellData.NOTE))

        if need_grid_data:
            # Use spreadsheets.get for full cell data
            request = self.spreadsheets.get(
                spreadsheetId=self.spreadsheet_id,
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
                    spreadsheetId=self.spreadsheet_id,
                    range=ranges[0],
                    valueRenderOption=value_render
                )
            else:
                # Multiple ranges - use values.batchGet
                request = self.spreadsheets.values().batchGet(
                    spreadsheetId=self.spreadsheet_id,
                    ranges=ranges,
                    valueRenderOption=value_render
                )

            return self._execute_with_retry(request)

    def write(self, data: List[dict]) -> dict:
        """Write to cells.

        Args:
            data: List of write operations
                [
                    {'range': 'Sheet1!A1', 'values': [[1, 2, 3], [4, 5, 6]]},
                    {'range': 'Sheet2!B5', 'values': [['text', '=SUM(A:A)']]},
                ]

                Each dict can have:
                - 'range': A1 notation (required)
                - 'values': 2D array (for value/formula writes)
                - 'format': Format dict (for formatting writes)
                - 'note': String (for note writes)

        Returns:
            Raw API response with update results.
            {
                'spreadsheetId': '...',
                'totalUpdatedRows': 10,
                'totalUpdatedColumns': 5,
                'totalUpdatedCells': 50,
                'responses': [...]
            }

        Behavior:
            - Formulas: Start with '=', automatically parsed
            - Clear values: values=[[]] or values=[['']]
            - Clear formatting: format={} (empty dict)
            - Multiple operations: Batched in single API call

        Examples:
            # Write values
            client.write([{
                'range': 'Sheet1!A1',
                'values': [[1, 2, 3], [4, 5, 6]]
            }])

            # Write formulas
            client.write([{
                'range': 'Sheet1!D1',
                'values': [['=SUM(A1:C1)'], ['=SUM(A2:C2)']]
            }])

            # Write values and format together
            client.write([
                {'range': 'Sheet1!A1', 'values': [['Total']]},
                {'range': 'Sheet1!A1', 'format': {
                    'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                    'textFormat': {'bold': True}
                }}
            ])

            # Write note
            client.write([{
                'range': 'Sheet1!A1',
                'note': 'Important cell!'
            }])

            # Batch write multiple ranges
            client.write([
                {'range': 'Sheet1!A1', 'values': [[1, 2, 3]]},
                {'range': 'Sheet2!B5', 'values': [[4, 5, 6]]},
                {'range': 'Sheet3!C10', 'values': [[7, 8, 9]]}
            ])
        """
        # Separate value writes from format/note writes
        value_writes = [d for d in data if 'values' in d]
        other_writes = [d for d in data if 'format' in d or 'note' in d]

        results = {}

        # Handle value writes with values API
        if value_writes:
            value_data = [{'range': d['range'], 'values': d['values']} for d in value_writes]
            body = {
                'valueInputOption': 'USER_ENTERED',
                'data': value_data
            }
            request = self.spreadsheets.values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            )
            results['values'] = self._execute_with_retry(request)

        # Handle format/note writes with batchUpdate
        if other_writes:
            # TODO: Implement format and note writes using batch_update
            # This requires converting to updateCells requests
            raise NotImplementedError("Format and note writes not yet implemented")

        return results.get('values', {})

    def metadata(self) -> dict:
        """Get spreadsheet metadata.

        Read-only view of spreadsheet structure without cell data.

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
            meta = client.metadata()
            for sheet in meta['sheets']:
                print(f"Sheet: {sheet['properties']['title']}")
                print(f"  ID: {sheet['properties']['sheetId']}")

            # Find sheet ID by name
            meta = client.metadata()
            sheet_id = next(
                s['properties']['sheetId']
                for s in meta['sheets']
                if s['properties']['title'] == 'Sales'
            )

            # List named ranges
            meta = client.metadata()
            for nr in meta.get('namedRanges', []):
                print(f"{nr['name']}: {nr['range']}")
        """
        request = self.spreadsheets.get(
            spreadsheetId=self.spreadsheet_id,
            includeGridData=False
        )
        return self._execute_with_retry(request)

    def structure(self, requests: List[dict]) -> dict:
        """Modify spreadsheet structure and metadata.

        Direct access to spreadsheets.batchUpdate API.
        Performs structural operations (not cell value writes).

        Args:
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
            client.structure([{
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
            sheet_id = 0  # From metadata()
            client.structure([{
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
            client.structure([{
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
            client.structure([
                {'addSheet': {'properties': {'title': 'Dashboard'}}},
                {'updateSheetProperties': {...}},
                {'autoResizeDimensions': {...}}
            ])
        """
        body = {'requests': requests}
        request = self.spreadsheets.batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body=body
        )
        return self._execute_with_retry(request)
