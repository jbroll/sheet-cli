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
    client = SheetsClient(args.spreadsheet_id)

    # Read all ranges
    response = client.read(args.ranges, types=CellData.VALUE | CellData.FORMULA)

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
    client = SheetsClient(args.spreadsheet_id)

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
    result = client.write(write_ops)

    # Output result summary
    if 'totalUpdatedCells' in result:
        print(f"Updated {result['totalUpdatedCells']} cells", file=sys.stderr)


def cmd_structure(args):
    """Execute structure operations from JSON stdin.

    Reads raw batch request JSON from stdin.
    """
    client = SheetsClient(args.spreadsheet_id)

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
    result = client.structure(requests)

    # Output result as JSON
    print(json.dumps(result, indent=2))


def cmd_metadata(args):
    """Get spreadsheet metadata.

    Outputs metadata as JSON.
    """
    client = SheetsClient(args.spreadsheet_id)
    result = client.metadata()
    print(json.dumps(result, indent=2))


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Google Sheets CLI - minimal wrapper for Sheets API v4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
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

  # Structure operations (batch API)
  echo '{"requests": [...]}' | sheet-cli structure SHEET_ID

  # Get metadata
  sheet-cli metadata SHEET_ID
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    # Read command
    parser_read = subparsers.add_parser('read', help='Read cell values')
    parser_read.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_read.add_argument('ranges', nargs='+', help='Cell or range (A1, A1:B10, Sheet1!A1)')
    parser_read.set_defaults(func=cmd_read)

    # Write command
    parser_write = subparsers.add_parser('write', help='Write cell values')
    parser_write.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_write.add_argument('cell_value_pairs', nargs='*', help='Alternating cell/range and value pairs')
    parser_write.set_defaults(func=cmd_write)

    # Structure command
    parser_structure = subparsers.add_parser('structure', help='Structure operations (batch API) from JSON stdin')
    parser_structure.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_structure.set_defaults(func=cmd_structure)

    # Metadata command
    parser_metadata = subparsers.add_parser('metadata', help='Get spreadsheet metadata')
    parser_metadata.add_argument('spreadsheet_id', help='Spreadsheet ID')
    parser_metadata.set_defaults(func=cmd_metadata)

    # Parse args and execute
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
