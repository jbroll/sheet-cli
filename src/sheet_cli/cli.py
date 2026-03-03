"""CLI command handlers."""

import argparse
import json
import sys
from typing import List, Dict, Any

from sheet_client import SheetsClient, CellData
from sheet_client.auth import get_credentials
from sheet_client.exceptions import SheetsClientError, AuthenticationError
from . import formats


def cmd_read(args):
    """Read values from specified cells/ranges.

    Outputs cell/value pairs (default) or Sheets API v4 JSON (--json).
    """
    client = SheetsClient()

    # Get metadata if needed (for --json or if no ranges specified)
    metadata = None
    if not args.ranges or getattr(args, 'json', False):
        metadata = client.meta_read(args.spreadsheet_id)

    # If no ranges specified, read all sheets
    if not args.ranges:
        # Build list of sheet names to read
        sheet_names = [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]

        if not sheet_names:
            print("No sheets found in spreadsheet", file=sys.stderr)
            sys.exit(1)

        # Use sheet names as ranges (reads all data from each sheet)
        args.ranges = sheet_names

    # Read all ranges
    response = client.read(args.spreadsheet_id, args.ranges, types=CellData.VALUE | CellData.FORMULA)

    # Output format: JSON (Sheets API v4) or text (cell/value pairs)
    if getattr(args, 'json', False):
        # Sheets API v4 format
        sheets_data = {}

        # Handle single range vs multiple ranges
        if 'values' in response:
            # Single range response
            range_str = response['range']
            values = response.get('values', [])
            # Extract sheet name from range (e.g., "Sheet1!A1:B10" -> "Sheet1")
            sheet_name = range_str.split('!')[0].strip("'\"") if '!' in range_str else 'Sheet1'
            sheets_data[sheet_name] = {
                'range': range_str.split('!')[1] if '!' in range_str else range_str,
                'values': values
            }
        elif 'valueRanges' in response:
            # Multiple ranges response
            for value_range in response['valueRanges']:
                range_str = value_range['range']
                values = value_range.get('values', [])
                # Extract sheet name
                sheet_name = range_str.split('!')[0].strip("'\"") if '!' in range_str else 'Sheet1'
                sheets_data[sheet_name] = {
                    'range': range_str.split('!')[1] if '!' in range_str else range_str,
                    'values': values
                }

        # Build Sheets API v4 output
        output = {
            'spreadsheetId': args.spreadsheet_id,
            'spreadsheetUrl': f'https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit',
            'title': metadata['properties']['title'] if metadata else '',
            'sheets': sheets_data
        }
        print(json.dumps(output, indent=2))
    else:
        # Text format (original behavior)
        result = {}

        # Handle single range vs multiple ranges
        if 'values' in response:
            # Single range response
            range_str = response['range']
            values = response.get('values', [])
            cell_values = formats.expand_range_to_cells(range_str, values)
            result.update(cell_values)
        elif 'valueRanges' in response:
            # Multiple ranges response
            for value_range in response['valueRanges']:
                range_str = value_range['range']
                values = value_range.get('values', [])
                cell_values = formats.expand_range_to_cells(range_str, values)
                result.update(cell_values)

        # Output as cell/value pairs
        output = formats.format_cell_value_pairs(result)
        print(output)


def cmd_write(args):
    """Write cells with values from command line or stdin.

    From command line: alternating cell/range and value pairs.
    From stdin: space-delimited or JSON format.
    """
    client = SheetsClient()

    # Check if we have command line cell/value pairs
    if args.cell_value_pairs:
        # Parse alternating cell value pairs from command line
        if len(args.cell_value_pairs) % 2 != 0:
            print("Error: Must provide alternating cell/range and value pairs", file=sys.stderr)
            sys.exit(1)

        data = {}
        for i in range(0, len(args.cell_value_pairs), 2):
            cell = args.cell_value_pairs[i]
            value = args.cell_value_pairs[i + 1]
            data[cell] = value
    else:
        # Read input from stdin
        input_text = formats.read_stdin()
        if not input_text:
            print("Error: No input provided. Use command line args or pipe data to stdin.", file=sys.stderr)
            sys.exit(1)

        # Parse input (auto-detect format)
        data = formats.parse_input(input_text)

    # Convert to write operations
    write_ops = []

    if isinstance(data, dict):
        # Check if it's range-based (JSON with ranges as keys)
        # or cell-based (space-delimited format)
        for key, value in data.items():
            if isinstance(value, list) and all(isinstance(v, list) for v in value):
                # Range-based: value is 2D array
                write_ops.append({
                    'range': key,
                    'values': value
                })
            else:
                # Cell-based: single cell with value
                write_ops.append({
                    'range': key,
                    'values': [[value]]
                })

    # Execute write
    result = client.write(args.spreadsheet_id, write_ops)

    # Output result summary
    if 'totalUpdatedCells' in result:
        print(f"Updated {result['totalUpdatedCells']} cells", file=sys.stderr)


def cmd_structure(args):
    """Execute structure operations from JSON stdin.

    Reads raw batch request JSON from stdin.
    """
    client = SheetsClient()

    # Read JSON from stdin
    input_text = formats.read_stdin()
    if not input_text:
        print("Error: No input provided. Pipe JSON to stdin.", file=sys.stderr)
        sys.exit(1)

    # Parse JSON
    try:
        data = json.loads(input_text)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract requests array
    if isinstance(data, dict) and 'requests' in data:
        requests = data['requests']
    elif isinstance(data, list):
        requests = data
    else:
        print("Error: Expected JSON with 'requests' array or array of requests", file=sys.stderr)
        sys.exit(1)

    # Execute structure operations
    result = client.meta_write(args.spreadsheet_id, requests)

    # Output result as JSON
    print(json.dumps(result, indent=2))


def cmd_metadata(args):
    """Get spreadsheet metadata.

    Outputs metadata as JSON.
    """
    client = SheetsClient()
    result = client.meta_read(args.spreadsheet_id)
    print(json.dumps(result, indent=2))


def cmd_copy(args):
    """Copy a range from one spreadsheet to another.

    Copies formulas by default. Use --value to copy computed values only.
    The destination is the top-left anchor cell; the full range is
    determined by the size of the source data.
    """
    client = SheetsClient()

    # Parse positional args: 3 = same sheet, 4 = different sheets
    if len(args.copy_args) == 3:
        source_id, source_range, dest_range = args.copy_args
        dest_id = source_id
    elif len(args.copy_args) == 4:
        source_id, source_range, dest_id, dest_range = args.copy_args
    else:
        print("Error: copy requires 3 or 4 arguments: SOURCE_ID SOURCE_RANGE [DEST_ID] DEST_RANGE",
              file=sys.stderr)
        sys.exit(1)

    # Read source — formula render preserves =... strings; value render flattens them
    read_types = CellData.VALUE if args.value else CellData.VALUE | CellData.FORMULA
    response = client.read(source_id, [source_range], types=read_types)

    # Extract 2D values array from response
    if 'values' in response:
        values = response['values']
    elif 'valueRanges' in response:
        values = response['valueRanges'][0].get('values', [])
    else:
        values = []

    if not values:
        print("Source range is empty.", file=sys.stderr)
        sys.exit(1)

    # Write to destination anchor — API expands from top-left
    client.write(dest_id, [{'range': dest_range, 'values': values}])

    rows = len(values)
    cols = max(len(row) for row in values)
    print(f"Copied {rows}x{cols} cells to {dest_id} {dest_range}")


def cmd_list(args):
    """List spreadsheets from Google Drive.

    Outputs a table of spreadsheets (ID, name, modified date) by default,
    or raw JSON with --json.
    """
    client = SheetsClient()
    files = client.list_spreadsheets(include_shared_drives=args.shared)

    if not files:
        print("No spreadsheets found.")
        return

    if getattr(args, 'json', False):
        print(json.dumps(files, indent=2))
    else:
        for f in files:
            modified = f.get('modifiedTime', '')[:10]  # YYYY-MM-DD
            name = f.get('name', '')
            fid = f.get('id', '')
            print(f"{fid}  {modified}  {name}")


_CREDENTIALS_SETUP = """
To set up authentication:

  1. Go to https://console.cloud.google.com/
  2. Create a project (or select an existing one)
  3. Enable the Google Sheets API and Google Drive API
  4. Go to APIs & Services > Credentials
  5. Create an OAuth 2.0 Client ID (Application type: Desktop app)
  6. Download the JSON and save it to:
       ~/.sheet-cli/credentials.json
  7. Run: sheet-cli auth
"""


def cmd_auth(args):
    """Authenticate with Google and cache the token.

    Forces a fresh OAuth flow, useful after scope changes or to switch accounts.
    """
    try:
        get_credentials(force_reauth=True)
    except AuthenticationError as e:
        msg = str(e)
        if 'Credentials file not found' in msg:
            print(f"Error: {msg}", file=sys.stderr)
            print(_CREDENTIALS_SETUP, file=sys.stderr)
        else:
            print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)
    print("Authentication successful. Token cached at ~/.sheet-cli/token.pickle")


def cmd_create(args):
    """Create a new spreadsheet.

    Outputs result as JSON including spreadsheet ID and URL.
    """
    client = SheetsClient()

    # Check if sheets config provided via stdin
    sheets = None
    if not sys.stdin.isatty():
        input_text = formats.read_stdin()
        if input_text:
            try:
                data = json.loads(input_text)
                if isinstance(data, dict) and 'sheets' in data:
                    sheets = data['sheets']
                elif isinstance(data, list):
                    sheets = data
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)

    result = client.create(args.title, sheets=sheets)
    print(json.dumps(result, indent=2))


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='sheet-cli',
        description='Google Sheets CLI - minimal wrapper for Sheets API v4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new spreadsheet
  sheet-cli create "My Spreadsheet"

  # Create with custom sheets (from stdin JSON)
  echo '[{"properties": {"title": "Sales"}}]' | sheet-cli create "My Report"

  # Read entire spreadsheet (all sheets)
  sheet-cli read SHEET_ID

  # Read with Sheets API v4 JSON output (for analysis tools)
  sheet-cli read --json SHEET_ID > data.json

  # Read multiple cells/ranges
  sheet-cli read SHEET_ID A1 A2 B1:B10 Sheet2!C1:C5

  # Write cells from command line (alternating cell value pairs)
  sheet-cli write SHEET_ID A1 "hello world" A2 123 A3 "=SUM(A1:A2)"

  # Write cells from stdin (space-delimited)
  echo 'A1 hello world
  A2 123
  A3 =SUM(A1:A2)' | sheet-cli write SHEET_ID

  # Write cells from stdin (JSON)
  echo '{"A1": "hello", "A2": 123}' | sheet-cli write SHEET_ID

  # Write metadata (batch API structure operations)
  echo '{"requests": [...]}' | sheet-cli meta_write SHEET_ID

  # Read metadata
  sheet-cli meta_read SHEET_ID
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # Read command
    parser_read = subparsers.add_parser('read', help='Read cell values')
    parser_read.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_read.add_argument('ranges', nargs='*', help='Cell or range (A1, A1:B10, Sheet1!A1). If omitted, reads all sheets.')
    parser_read.add_argument('--json', action='store_true', help='Output in Sheets API v4 JSON format (compatible with analysis tools)')
    parser_read.set_defaults(func=cmd_read)

    # Write command
    parser_write = subparsers.add_parser('write', help='Write cell values')
    parser_write.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_write.add_argument('cell_value_pairs', nargs='*', help='Alternating cell/range and value pairs')
    parser_write.set_defaults(func=cmd_write)

    # meta_write command (was: structure)
    parser_meta_write = subparsers.add_parser('meta_write', help='Write metadata (batch API structure operations) from JSON stdin')
    parser_meta_write.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_meta_write.set_defaults(func=cmd_structure)

    # meta_read command (was: metadata)
    parser_meta_read = subparsers.add_parser('meta_read', help='Read spreadsheet metadata')
    parser_meta_read.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_meta_read.set_defaults(func=cmd_metadata)

    # create command
    parser_create = subparsers.add_parser('create', help='Create a new spreadsheet')
    parser_create.add_argument('title', help='Spreadsheet title')
    parser_create.set_defaults(func=cmd_create)

    # copy command
    parser_copy = subparsers.add_parser('copy', help='Copy a range between spreadsheets',
                                        description='Copy a range from one spreadsheet to another. '
                                                    'Formulas are preserved by default. '
                                                    'The destination is the top-left anchor cell.')
    parser_copy.add_argument('copy_args', nargs='+',
                             metavar='arg',
                             help='SOURCE_ID SOURCE_RANGE DEST_RANGE  '
                                  '(same spreadsheet) or  '
                                  'SOURCE_ID SOURCE_RANGE DEST_ID DEST_RANGE  '
                                  '(different spreadsheets)')
    parser_copy.add_argument('--value', action='store_true',
                             help='Copy computed values only, not formulas')
    parser_copy.set_defaults(func=cmd_copy)

    # list command
    parser_list = subparsers.add_parser('list', help='List spreadsheets from Google Drive',
                                        description='List spreadsheets visible to the authenticated user. '
                                                    'Outputs ID, modified date, and name. '
                                                    'Use the ID with other sheet-cli commands.')
    parser_list.add_argument('--shared', action='store_true',
                             help='Include files from Shared Drives (team/org drives)')
    parser_list.add_argument('--json', action='store_true',
                             help='Output raw JSON instead of text table')
    parser_list.set_defaults(func=cmd_list)

    # auth command
    parser_auth = subparsers.add_parser('auth', help='Authenticate and cache OAuth token')
    parser_auth.set_defaults(func=cmd_auth)

    # Parse args and execute
    args = parser.parse_args()
    try:
        args.func(args)
    except SheetsClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
