"""Utility functions for A1 notation and grid range conversion."""

import re
from typing import Dict, Optional


def column_to_index(column: str) -> int:
    """Convert column letter(s) to zero-based index.

    Args:
        column: Column letter(s) like 'A', 'Z', 'AA', 'AB'

    Returns:
        Zero-based column index (A=0, Z=25, AA=26, etc.)

    Examples:
        >>> column_to_index('A')
        0
        >>> column_to_index('Z')
        25
        >>> column_to_index('AA')
        26
    """
    result = 0
    for char in column.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def index_to_column(index: int) -> str:
    """Convert zero-based index to column letter(s).

    Args:
        index: Zero-based column index

    Returns:
        Column letter(s) like 'A', 'Z', 'AA', 'AB'

    Examples:
        >>> index_to_column(0)
        'A'
        >>> index_to_column(25)
        'Z'
        >>> index_to_column(26)
        'AA'
    """
    result = ""
    index += 1  # Convert to 1-based
    while index > 0:
        index -= 1  # Adjust for 0-based modulo
        result = chr(ord('A') + (index % 26)) + result
        index //= 26
    return result


def a1_to_grid_range(a1_notation: str, sheet_id: int = 0) -> Dict:
    """Convert A1 notation to GridRange format for batch operations.

    Args:
        a1_notation: A1 notation like 'Sheet1!A1:C10' or 'A1:C10'
        sheet_id: Sheet ID (default 0)

    Returns:
        GridRange dictionary with zero-based, half-open indices

    Examples:
        >>> a1_to_grid_range('A1:C10', 0)
        {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 10, 'startColumnIndex': 0, 'endColumnIndex': 3}
        >>> a1_to_grid_range('Sheet1!A1:C10', 0)
        {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 10, 'startColumnIndex': 0, 'endColumnIndex': 3}
    """
    # Remove sheet name if present
    if '!' in a1_notation:
        a1_notation = a1_notation.split('!')[1]

    # Parse A1 notation
    match = re.match(r'^([A-Z]+)(\d+):([A-Z]+)(\d+)$', a1_notation.upper())
    if not match:
        raise ValueError(f"Invalid A1 notation: {a1_notation}")

    start_col, start_row, end_col, end_row = match.groups()

    return {
        'sheetId': sheet_id,
        'startRowIndex': int(start_row) - 1,  # Convert to 0-based
        'endRowIndex': int(end_row),  # Exclusive end
        'startColumnIndex': column_to_index(start_col),
        'endColumnIndex': column_to_index(end_col) + 1  # Exclusive end
    }
