"""Example 2: Batch formatting via spreadsheets.batchUpdate.

Demonstrates:
- meta_read() to discover sheet IDs (required for GridRange)
- write() for cell values
- meta_write() for formatting and structure changes (formatting, freeze,
  auto-resize, borders, etc.) — all in a single batched call
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient


def main():
    # Replace with your spreadsheet ID
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'

    client = SheetsClient()

    # Sheet ID is required for batchUpdate GridRange — pull it from metadata.
    meta = client.meta_read(SPREADSHEET_ID)
    sheet_id = meta['sheets'][0]['properties']['sheetId']
    print(f"Working with sheet ID: {sheet_id}")

    print("\n=== Writing Sales Data ===")
    client.write(SPREADSHEET_ID, [
        {'range': 'Sheet1!A1',
         'values': [['Date', 'Product', 'Amount', 'Status']]},
        {'range': 'Sheet1!A2',
         'values': [
             ['2024-01-15', 'Widget A', 1250.50, 'Completed'],
             ['2024-01-16', 'Widget B',  890.00, 'Pending'],
             ['2024-01-17', 'Widget A', 2100.75, 'Completed'],
             ['2024-01-18', 'Widget C',  450.25, 'Cancelled'],
         ]},
    ])
    print("Data written")

    print("\n=== Applying Batch Formatting (8 ops, single call) ===")
    client.meta_write(SPREADSHEET_ID, [
        # 1. Header row: gray bg, bold, centered
        {'repeatCell': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 0, 'endRowIndex': 1,
                      'startColumnIndex': 0, 'endColumnIndex': 4},
            'cell': {'userEnteredFormat': {
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                'textFormat': {'bold': True, 'fontSize': 11},
                'horizontalAlignment': 'CENTER',
            }},
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)',
        }},

        # 2. Freeze header row
        {'updateSheetProperties': {
            'properties': {'sheetId': sheet_id,
                           'gridProperties': {'frozenRowCount': 1}},
            'fields': 'gridProperties.frozenRowCount',
        }},

        # 3. Auto-resize all columns
        {'autoResizeDimensions': {
            'dimensions': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
                           'startIndex': 0, 'endIndex': 4},
        }},

        # 4. Light blue alternating-row tint (data rows)
        {'repeatCell': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 2, 'endRowIndex': 5,
                      'startColumnIndex': 0, 'endColumnIndex': 4},
            'cell': {'userEnteredFormat': {
                'backgroundColor': {'red': 0.95, 'green': 0.97, 'blue': 1.0},
            }},
            'fields': 'userEnteredFormat.backgroundColor',
        }},

        # 5. Currency format on Amount column
        {'repeatCell': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 1, 'endRowIndex': 5,
                      'startColumnIndex': 2, 'endColumnIndex': 3},
            'cell': {'userEnteredFormat': {
                'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'},
            }},
            'fields': 'userEnteredFormat.numberFormat',
        }},

        # 6. Green for "Completed" (row index 1)
        {'repeatCell': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 1, 'endRowIndex': 2,
                      'startColumnIndex': 3, 'endColumnIndex': 4},
            'cell': {'userEnteredFormat': {
                'backgroundColor': {'red': 0.85, 'green': 1.0, 'blue': 0.85},
            }},
            'fields': 'userEnteredFormat.backgroundColor',
        }},

        # 7. Red for "Cancelled" (row index 4)
        {'repeatCell': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 4, 'endRowIndex': 5,
                      'startColumnIndex': 3, 'endColumnIndex': 4},
            'cell': {'userEnteredFormat': {
                'backgroundColor': {'red': 1.0, 'green': 0.85, 'blue': 0.85},
            }},
            'fields': 'userEnteredFormat.backgroundColor',
        }},

        # 8. Borders around the table
        {'updateBorders': {
            'range': {'sheetId': sheet_id,
                      'startRowIndex': 0, 'endRowIndex': 5,
                      'startColumnIndex': 0, 'endColumnIndex': 4},
            'top':             {'style': 'SOLID', 'width': 1},
            'bottom':          {'style': 'SOLID', 'width': 1},
            'left':            {'style': 'SOLID', 'width': 1},
            'right':           {'style': 'SOLID', 'width': 1},
            'innerHorizontal': {'style': 'SOLID', 'width': 1},
            'innerVertical':   {'style': 'SOLID', 'width': 1},
        }},
    ])

    print("Applied 8 formatting operations")
    print(f"URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


if __name__ == '__main__':
    main()
