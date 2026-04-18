"""Example 1: Basic read/write operations with Google Sheets.

Demonstrates:
- Writing values and formulas in batched calls
- Reading values, formulas, and multiple ranges in one round-trip
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient, CellData


def main():
    # Replace with your spreadsheet ID
    # (from URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'

    # Constructor takes no spreadsheet_id — pass it to each method.
    # First run opens a browser for OAuth; subsequent runs reuse the cached token.
    client = SheetsClient()

    print("=== Writing Headers and Data ===")
    client.write(SPREADSHEET_ID, [
        {'range': 'Sheet1!A1',
         'values': [['Name', 'Age', 'Department', 'Email']]},
        {'range': 'Sheet1!A2',
         'values': [
             ['Alice Smith',    30, 'Engineering', 'alice@example.com'],
             ['Bob Johnson',    25, 'Marketing',   'bob@example.com'],
             ['Charlie Brown',  35, 'Sales',       'charlie@example.com'],
         ]},
    ])
    print("Data written successfully")

    print("\n=== Reading Data (values only) ===")
    result = client.read(SPREADSHEET_ID, ['Sheet1!A1:D4'])
    for row in result.get('values', []):
        print(row)

    print("\n=== Appending One More Row ===")
    client.write(SPREADSHEET_ID, [{
        'range': 'Sheet1!A5',
        'values': [['Diana Prince', 28, 'Engineering', 'diana@example.com']],
    }])
    print("Appended new row")

    print("\n=== Writing and Reading a Formula ===")
    client.write(SPREADSHEET_ID, [{
        'range': 'Sheet1!E2',
        'values': [['=SUM(B2:B5)']],
    }])

    # FORMULA flag returns the formula text instead of the computed value
    result = client.read(SPREADSHEET_ID, ['Sheet1!E2'], types=CellData.FORMULA)
    print(f"Formula:        {result.get('values', [])}")

    # Default (VALUE) returns the computed value
    result = client.read(SPREADSHEET_ID, ['Sheet1!E2'])
    print(f"Computed value: {result.get('values', [])}")

    print("\n=== Reading Multiple Ranges in One Call ===")
    result = client.read(SPREADSHEET_ID, ['Sheet1!A1:B2', 'Sheet1!D1:D3'])
    # Multi-range reads return 'valueRanges'.
    for vr in result.get('valueRanges', []):
        print(f"Range:  {vr['range']}")
        print(f"Values: {vr.get('values', [])}")


if __name__ == '__main__':
    main()
