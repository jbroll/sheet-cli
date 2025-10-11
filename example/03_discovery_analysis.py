"""Example 3: Discovery and analysis with Google Sheets.

This example demonstrates:
- Using metadata() to analyze sheet structure
- Using read() with CellData.FORMAT flag to find formatted cells
- Finding formulas in cells
- Detecting data boundaries
- Understanding sheet properties
"""

import sys
sys.path.insert(0, '../src')

from src import SheetsClient, CellData


def analyze_spreadsheet(spreadsheet_id: str):
    """Analyze a spreadsheet and print detailed information."""
    client = SheetsClient(spreadsheet_id)

    print("=== Getting Spreadsheet Metadata ===")
    meta = client.metadata()

    # Spreadsheet properties
    print(f"\nSpreadsheet Title: {meta['properties']['title']}")
    print(f"Locale: {meta['properties']['locale']}")
    print(f"Time Zone: {meta['properties']['timeZone']}")

    # Analyze each sheet
    print(f"\n=== Analyzing {len(meta['sheets'])} Sheet(s) ===")

    for sheet_idx, sheet in enumerate(meta['sheets']):
        props = sheet['properties']
        print(f"\n--- Sheet {sheet_idx + 1}: {props['title']} ---")
        print(f"Sheet ID: {props['sheetId']}")

        # Grid properties
        grid = props['gridProperties']
        print(f"Dimensions: {grid['rowCount']} rows x {grid['columnCount']} columns")

        if 'frozenRowCount' in grid and grid['frozenRowCount'] > 0:
            print(f"Frozen rows: {grid['frozenRowCount']}")
        if 'frozenColumnCount' in grid and grid['frozenColumnCount'] > 0:
            print(f"Frozen columns: {grid['frozenColumnCount']}")


def find_formulas(spreadsheet_id: str, sheet_name: str = 'Sheet1'):
    """Find all formulas in a sheet."""
    client = SheetsClient(spreadsheet_id)

    print(f"\n=== Finding Formulas in {sheet_name} ===")

    # Read with grid data to access formulas
    result = client.read([f'{sheet_name}!A1:Z100'], types=CellData.VALUE | CellData.FORMAT)

    # If we got grid data, analyze it
    if 'sheets' in result:
        for sheet in result['sheets']:
            if 'data' not in sheet:
                continue

            formulas_found = []
            for row_idx, row in enumerate(sheet['data'][0].get('rowData', [])):
                for col_idx, cell in enumerate(row.get('values', [])):
                    if 'userEnteredValue' in cell:
                        uev = cell['userEnteredValue']
                        if 'formulaValue' in uev:
                            formulas_found.append({
                                'row': row_idx + 1,  # 1-based for display
                                'col': col_idx + 1,
                                'formula': uev['formulaValue']
                            })

            if formulas_found:
                print(f"Found {len(formulas_found)} formula(s):")
                for f in formulas_found[:10]:  # Show first 10
                    print(f"  Row {f['row']}, Col {f['col']}: {f['formula']}")
            else:
                print("No formulas found")
    else:
        print("No grid data available (formulas require grid data)")


def find_data_extent(spreadsheet_id: str, sheet_name: str = 'Sheet1'):
    """Find actual data extent in a sheet."""
    client = SheetsClient(spreadsheet_id)

    print(f"\n=== Finding Data Extent in {sheet_name} ===")

    # Read values to find last row/column with data
    result = client.read([f'{sheet_name}!A:Z'])

    values = result.get('values', [])
    if not values:
        print("Sheet is empty")
        return

    last_row = len(values)
    max_col = max(len(row) for row in values) if values else 0

    print(f"Data extent: {last_row} rows x {max_col} columns")
    print(f"Last cell with data: approximately column {max_col}, row {last_row}")

    # Show sample of first few cells
    print("\nFirst 3x3 cells:")
    for row_idx in range(min(3, len(values))):
        row_display = values[row_idx][:3] if len(values[row_idx]) >= 3 else values[row_idx]
        print(f"  Row {row_idx + 1}: {row_display}")


def check_for_data_and_write(spreadsheet_id: str):
    """Example: Check if sheet has data before deciding where to write."""
    client = SheetsClient(spreadsheet_id)

    print("\n=== Smart Write Pattern ===")

    # Read to check for existing data
    result = client.read(['Sheet1!A:A'])
    values = result.get('values', [])
    has_data = len(values) > 0

    if has_data:
        print(f"Sheet has {len(values)} rows - writing to next row")
        next_row = len(values) + 1
        client.write([{
            'range': f'Sheet1!A{next_row}',
            'values': [['New', 'Appended', 'Row']]
        }])
    else:
        print("Sheet is empty - writing headers and data")
        client.write([
            {'range': 'Sheet1!A1', 'values': [['Header 1', 'Header 2', 'Header 3']]},
            {'range': 'Sheet1!A2', 'values': [['Data 1', 'Data 2', 'Data 3']]}
        ])


def main():
    # Replace with your spreadsheet ID
    SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'

    analyze_spreadsheet(SPREADSHEET_ID)
    find_formulas(SPREADSHEET_ID)
    find_data_extent(SPREADSHEET_ID)
    check_for_data_and_write(SPREADSHEET_ID)


if __name__ == '__main__':
    main()
