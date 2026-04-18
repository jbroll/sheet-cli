"""Example 3: Discovery and analysis with Google Sheets.

Demonstrates:
- meta_read() to inspect spreadsheet and sheet structure
- read() with the FORMULA flag to find formulas in a sheet
- Detecting data extent (last row/column with values)
- Smart-write pattern (append if data exists, otherwise seed headers)
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient, CellData


def analyze_spreadsheet(client: SheetsClient, spreadsheet_id: str):
    """Print spreadsheet metadata and per-sheet structure."""
    print("=== Spreadsheet Metadata ===")
    meta = client.meta_read(spreadsheet_id)

    props = meta['properties']
    print(f"Title:     {props['title']}")
    print(f"Locale:    {props['locale']}")
    print(f"Time Zone: {props['timeZone']}")

    print(f"\n=== {len(meta['sheets'])} Sheet(s) ===")
    for idx, sheet in enumerate(meta['sheets']):
        sp = sheet['properties']
        grid = sp['gridProperties']
        print(f"\n--- Sheet {idx + 1}: {sp['title']} ---")
        print(f"  Sheet ID:   {sp['sheetId']}")
        print(f"  Dimensions: {grid['rowCount']} rows x {grid['columnCount']} cols")
        if grid.get('frozenRowCount'):
            print(f"  Frozen rows:    {grid['frozenRowCount']}")
        if grid.get('frozenColumnCount'):
            print(f"  Frozen columns: {grid['frozenColumnCount']}")


def find_formulas(client: SheetsClient, spreadsheet_id: str,
                  sheet_name: str = 'Sheet1'):
    """List formulas in a sheet using read() with the FORMULA flag."""
    print(f"\n=== Finding Formulas in {sheet_name} ===")

    # FORMULA flag: cells holding formulas come back as the formula string
    # (e.g. '=SUM(A1:A10)'). Plain cells come back as their literal value.
    result = client.read(spreadsheet_id, [f'{sheet_name}!A1:Z100'],
                         types=CellData.FORMULA)

    formulas = []
    for row_idx, row in enumerate(result.get('values', [])):
        for col_idx, cell in enumerate(row):
            if isinstance(cell, str) and cell.startswith('='):
                formulas.append((row_idx + 1, col_idx + 1, cell))

    if not formulas:
        print("No formulas found")
        return

    print(f"Found {len(formulas)} formula(s):")
    for row, col, formula in formulas[:10]:
        print(f"  Row {row}, Col {col}: {formula}")


def find_data_extent(client: SheetsClient, spreadsheet_id: str,
                     sheet_name: str = 'Sheet1'):
    """Find the actual rectangle of data in a sheet."""
    print(f"\n=== Data Extent in {sheet_name} ===")

    result = client.read(spreadsheet_id, [f'{sheet_name}!A:Z'])
    values = result.get('values', [])
    if not values:
        print("Sheet is empty")
        return

    last_row = len(values)
    max_col = max(len(row) for row in values)
    print(f"Extent: {last_row} rows x {max_col} columns")

    print("\nFirst 3x3 cells:")
    for row_idx in range(min(3, last_row)):
        print(f"  Row {row_idx + 1}: {values[row_idx][:3]}")


def check_for_data_and_write(client: SheetsClient, spreadsheet_id: str):
    """Smart-write pattern: append if data exists, else seed headers."""
    print("\n=== Smart Write Pattern ===")

    result = client.read(spreadsheet_id, ['Sheet1!A:A'])
    values = result.get('values', [])

    if values:
        next_row = len(values) + 1
        print(f"Sheet has {len(values)} rows — appending to row {next_row}")
        client.write(spreadsheet_id, [{
            'range': f'Sheet1!A{next_row}',
            'values': [['New', 'Appended', 'Row']],
        }])
    else:
        print("Sheet is empty — writing headers and data")
        client.write(spreadsheet_id, [
            {'range': 'Sheet1!A1', 'values': [['Header 1', 'Header 2', 'Header 3']]},
            {'range': 'Sheet1!A2', 'values': [['Data 1',   'Data 2',   'Data 3']]},
        ])


def main():
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'
    client = SheetsClient()
    analyze_spreadsheet(client, SPREADSHEET_ID)
    find_formulas(client, SPREADSHEET_ID)
    find_data_extent(client, SPREADSHEET_ID)
    check_for_data_and_write(client, SPREADSHEET_ID)


if __name__ == '__main__':
    main()
