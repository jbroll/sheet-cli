"""Format handling for CLI input/output."""

import json
import sys
from typing import Dict, List, Any, Tuple, Union


def parse_cell_value_pairs(text: str) -> Dict[str, Any]:
    """Parse space-delimited cell/value pairs.

    Format: "cell value" or "cell =formula"
    Splits on first space only. Everything after is the value.
    Formulas are indicated by leading '=' (just like in sheets).

    Args:
        text: Input text with cell/value pairs

    Returns:
        Dict mapping cell addresses to values

    Examples:
        >>> parse_cell_value_pairs("A1 hello world\\nA2 123\\nA3 =SUM(A1:A2)")
        {'A1': 'hello world', 'A2': '123', 'A3': '=SUM(A1:A2)'}
    """
    result = {}

    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Split on first space only
        parts = line.split(' ', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid format: '{line}'. Expected 'cell value'")

        cell, value = parts
        result[cell] = value

    return result


def format_cell_value_pairs(data: Dict[str, Any]) -> str:
    """Format cell/value pairs for output.

    Args:
        data: Dict mapping cell addresses to values

    Returns:
        Space-delimited text output

    Examples:
        >>> format_cell_value_pairs({'A1': 'hello', 'A2': 123, 'A3': '=SUM(A1:A2)'})
        'A1 hello\\nA2 123\\nA3 =SUM(A1:A2)'
    """
    lines = []
    for cell, value in data.items():
        # Convert value to string, preserve formulas
        value_str = str(value) if value is not None else ''
        lines.append(f"{cell} {value_str}")

    return '\n'.join(lines)


def expand_range_to_cells(range_str: str, values: List[List[Any]]) -> Dict[str, Any]:
    """Expand a range and its values to individual cell/value pairs.

    Args:
        range_str: A1 notation range (e.g., "A1:B2" or "Sheet1!A1:B2")
        values: 2D array of values

    Returns:
        Dict mapping individual cells to values

    Examples:
        >>> expand_range_to_cells("A1:B2", [["a1", "b1"], ["a2", "b2"]])
        {'A1': 'a1', 'B1': 'b1', 'A2': 'a2', 'B2': 'b2'}
    """
    from sheet_client.utils import a1_to_grid_range, index_to_column

    # Normalize single cell references (A1 -> A1:A1)
    # Google Sheets API returns single cells without the colon
    normalized_range = range_str
    if '!' in range_str:
        sheet_name, cell_part = range_str.split('!', 1)
        if ':' not in cell_part:
            normalized_range = f"{sheet_name}!{cell_part}:{cell_part}"
    elif ':' not in range_str:
        normalized_range = f"{range_str}:{range_str}"

    # Parse the range
    grid_range = a1_to_grid_range(normalized_range)

    # Extract sheet name if present
    sheet_prefix = ""
    if '!' in range_str:
        sheet_prefix = range_str.split('!')[0] + '!'

    result = {}
    start_row = grid_range.get('startRowIndex', 0)
    start_col = grid_range.get('startColumnIndex', 0)

    for row_idx, row_values in enumerate(values):
        for col_idx, value in enumerate(row_values):
            actual_row = start_row + row_idx + 1  # 1-indexed
            actual_col = start_col + col_idx
            col_letter = index_to_column(actual_col)
            cell_addr = f"{sheet_prefix}{col_letter}{actual_row}"
            result[cell_addr] = value

    return result


def detect_format(text: str) -> str:
    """Auto-detect input format (JSON or space-delimited).

    Args:
        text: Input text

    Returns:
        'json' or 'cell_value'
    """
    text = text.strip()

    if text.startswith('{') or text.startswith('['):
        return 'json'

    return 'cell_value'


def parse_input(text: str) -> Union[Dict[str, Any], Dict[str, List[List[Any]]]]:
    """Parse input in either format, auto-detecting.

    Args:
        text: Input text (JSON or space-delimited)

    Returns:
        Dict of cell/value pairs or range/values pairs
    """
    format_type = detect_format(text)

    if format_type == 'json':
        return json.loads(text)
    else:
        return parse_cell_value_pairs(text)


def read_stdin() -> str:
    """Read all input from stdin."""
    if sys.stdin.isatty():
        # No piped input
        return ""
    return sys.stdin.read()
