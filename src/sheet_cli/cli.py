"""CLI command handlers."""

import argparse
import json
import sys
from typing import List, Dict, Any

from sheet_client import SheetsClient, CellData
from . import formats


def cmd_read(args):
    """Read values from specified cells/ranges.

    Outputs cell/value pairs to stdout.
    """
    client = SheetsClient()

    # If no ranges specified, read all sheets
    if not args.ranges:
        # Get metadata to discover all sheets
        metadata = client.meta_read(args.spreadsheet_id)

        # Build list of sheet names to read
        sheet_names = [sheet['properties']['title'] for sheet in metadata.get('sheets', [])]

        if not sheet_names:
            print("No sheets found in spreadsheet", file=sys.stderr)
            sys.exit(1)

        # Use sheet names as ranges (reads all data from each sheet)
        args.ranges = sheet_names

    # Read all ranges
    response = client.read(args.spreadsheet_id, args.ranges, types=CellData.VALUE | CellData.FORMULA)

    # Extract values from response
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

    # Parse args and execute
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
