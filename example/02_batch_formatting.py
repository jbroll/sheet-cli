"""Example 2: Batch formatting operations with Google Sheets.

This example demonstrates:
- Using metadata() to get sheet information
- Using write() for data
- Using structure() for formatting
- Creating a formatted table with colors, borders, and frozen rows
"""

import sys
sys.path.insert(0, '../src')

from src import SheetsClient


def main():
    # Replace with your spreadsheet ID
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'

    # Initialize client
    client = SheetsClient(SPREADSHEET_ID)

    # Get sheet ID (needed for structure operations)
    meta = client.metadata()
    sheet_id = meta['sheets'][0]['properties']['sheetId']
    print(f"Working with sheet ID: {sheet_id}")

    print("\n=== Writing Sales Data ===")
    client.write([
        {
            'range': 'Sheet1!A1',
            'values': [['Date', 'Product', 'Amount', 'Status']]
        },
        {
            'range': 'Sheet1!A2',
            'values': [
                ['2024-01-15', 'Widget A', 1250.50, 'Completed'],
                ['2024-01-16', 'Widget B', 890.00, 'Pending'],
                ['2024-01-17', 'Widget A', 2100.75, 'Completed'],
                ['2024-01-18', 'Widget C', 450.25, 'Cancelled']
            ]
        }
    ])
    print("Data written")

    print("\n=== Applying Batch Formatting ===")
    client.structure([
        # 1. Format header row (gray background, bold text, centered)
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': 4
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                        'textFormat': {'bold': True, 'fontSize': 11},
                        'horizontalAlignment': 'CENTER'
                    }
                },
                'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
            }
        },

        # 2. Freeze header row
        {
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'frozenRowCount': 1}
                },
                'fields': 'gridProperties.frozenRowCount'
            }
        },

        # 3. Auto-resize all columns
        {
            'autoResizeDimensions': {
                'dimensions': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': 0,
                    'endIndex': 4
                }
            }
        },

        # 4. Add alternating row colors (light blue for even rows)
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 2,  # Skip header
                    'endRowIndex': 6,
                    'startColumnIndex': 0,
                    'endColumnIndex': 4
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.95, 'green': 0.97, 'blue': 1.0}
                    }
                },
                'fields': 'userEnteredFormat.backgroundColor'
            }
        },

        # 5. Format amount column as currency
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 1,
                    'endRowIndex': 6,
                    'startColumnIndex': 2,
                    'endColumnIndex': 3
                },
                'cell': {
                    'userEnteredFormat': {
                        'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
                    }
                },
                'fields': 'userEnteredFormat.numberFormat'
            }
        },

        # 6. Color-code status column - Green for "Completed"
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 1,
                    'endRowIndex': 2,
                    'startColumnIndex': 3,
                    'endColumnIndex': 4
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.85, 'green': 1.0, 'blue': 0.85}
                    }
                },
                'fields': 'userEnteredFormat.backgroundColor'
            }
        },

        # 7. Red for "Cancelled"
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 4,
                    'endRowIndex': 5,
                    'startColumnIndex': 3,
                    'endColumnIndex': 4
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 1.0, 'green': 0.85, 'blue': 0.85}
                    }
                },
                'fields': 'userEnteredFormat.backgroundColor'
            }
        },

        # 8. Add borders around the table
        {
            'updateBorders': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 5,
                    'startColumnIndex': 0,
                    'endColumnIndex': 4
                },
                'top': {'style': 'SOLID', 'width': 1},
                'bottom': {'style': 'SOLID', 'width': 1},
                'left': {'style': 'SOLID', 'width': 1},
                'right': {'style': 'SOLID', 'width': 1},
                'innerHorizontal': {'style': 'SOLID', 'width': 1},
                'innerVertical': {'style': 'SOLID', 'width': 1}
            }
        }
    ])

    print("Applied 8 formatting operations")
    print(f"Spreadsheet URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


if __name__ == '__main__':
    main()
