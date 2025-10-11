"""Example 1: Basic read/write operations with Google Sheets.

This example demonstrates:
- Reading values from a sheet
- Writing values to a sheet
- Reading formulas
- Using the simplified 4-method API
"""

import sys
sys.path.insert(0, '../src')

from src import SheetsClient, CellData


def main():
    # Replace with your spreadsheet ID
    # (from URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'

    # Initialize client (will open browser on first run for OAuth)
    client = SheetsClient(SPREADSHEET_ID)

    print("=== Writing Headers and Data ===")
    client.write([
        {
            'range': 'Sheet1!A1',
            'values': [['Name', 'Age', 'Department', 'Email']]
        },
        {
            'range': 'Sheet1!A2',
            'values': [
                ['Alice Smith', 30, 'Engineering', 'alice@example.com'],
                ['Bob Johnson', 25, 'Marketing', 'bob@example.com'],
                ['Charlie Brown', 35, 'Sales', 'charlie@example.com']
            ]
        }
    ])
    print("Data written successfully")

    print("\n=== Reading Data (Values Only) ===")
    result = client.read(['Sheet1!A1:D4'])
    values = result.get('values', [])
    for row in values:
        print(row)

    print("\n=== Writing More Data ===")
    client.write([{
        'range': 'Sheet1!A5',
        'values': [['Diana Prince', 28, 'Engineering', 'diana@example.com']]
    }])
    print("Appended new row")

    print("\n=== Reading All Data ===")
    result = client.read(['Sheet1!A1:D10'])
    values = result.get('values', [])
    print(f"Found {len(values)} rows:")
    for row in values:
        print(row)

    print("\n=== Writing and Reading Formulas ===")
    # Write a formula
    client.write([{
        'range': 'Sheet1!E2',
        'values': [['=SUM(B2:B5)']]
    }])

    # Read as formula
    result = client.read(['Sheet1!E2'], types=CellData.FORMULA)
    print(f"Formula: {result.get('values', [])}")

    # Read computed value
    result = client.read(['Sheet1!E2'], types=CellData.VALUE)
    print(f"Computed value: {result.get('values', [])}")

    print("\n=== Reading Multiple Ranges ===")
    result = client.read(['Sheet1!A1:B2', 'Sheet1!D1:D3'])
    if 'valueRanges' in result:
        for value_range in result['valueRanges']:
            print(f"Range: {value_range['range']}")
            print(f"Values: {value_range.get('values', [])}")
    else:
        # Single range result
        print(f"Range: {result.get('range')}")
        print(f"Values: {result.get('values', [])}")


if __name__ == '__main__':
    main()
