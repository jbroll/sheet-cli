# API Reference

Complete technical reference for Google Sheets CLI - simplified 4-method API.

## Installation

```bash
pip install -r requirements.txt
```

Dependencies:
- `google-api-python-client>=2.0.0`
- `google-auth>=2.0.0`
- `google-auth-oauthlib>=0.5.0`
- `google-auth-httplib2>=0.1.0`

## Authentication Setup

1. Create OAuth 2.0 Client ID in [Google Cloud Console](https://console.cloud.google.com)
2. Go to APIs & Services → Credentials
3. Create Credentials → OAuth 2.0 Client ID → Desktop App
4. Download as `~/.sheet-cli/credentials.json`

First run opens browser for authorization. Token cached to `~/.sheet-cli/token.pickle` and auto-refreshes.

**Security**: Credentials stored in `~/.sheet-cli/` with secure permissions (directory: 700, files: 600).

## SheetsClient

### Constructor

```python
from sheet_client import SheetsClient, CellData

client = SheetsClient(
    credentials_path: str = None,  # Defaults to ~/.sheet-cli/credentials.json
    token_path: str = None         # Defaults to ~/.sheet-cli/token.pickle
)
```

**Parameters:**
- `credentials_path` - Path to OAuth client credentials JSON (defaults to `~/.sheet-cli/credentials.json`)
- `token_path` - Path to save/load cached token (defaults to `~/.sheet-cli/token.pickle`)

**Behavior:**
- First run opens browser for OAuth authorization
- Token cached and auto-refreshed
- Raises `AuthenticationError` if OAuth fails
- No default spreadsheet - specify per method call

## Core API - Four Methods

The entire API consists of four methods with perfect symmetry:

| Operation | Read | Write |
|-----------|------|-------|
| **Cell Data** | `read()` | `write()` |
| **Metadata** | `meta_read()` | `meta_write()` |

1. **`read(spreadsheet_id, ranges, types)`** - Read cell data
2. **`write(spreadsheet_id, data)`** - Write cell data
3. **`meta_read(spreadsheet_id)`** - Read metadata/structure
4. **`meta_write(spreadsheet_id, requests)`** - Write metadata/structure

All methods require `spreadsheet_id` as the first parameter.

## CellData Flags

```python
from enum import IntFlag

class CellData(IntFlag):
    VALUE = 1      # Cell values (numbers, strings, booleans)
    FORMULA = 2    # Formulas (=SUM(A:A))
    FORMAT = 4     # Formatting (colors, fonts, borders, number formats)
    NOTE = 8       # Cell notes/comments
```

Combine flags with bitwise OR:
```python
# Values and formulas
client.read(['Sheet1!A1:C10'], types=CellData.VALUE | CellData.FORMULA)

# Everything
client.read(['Sheet1!A1:C10'], types=CellData.VALUE | CellData.FORMULA | CellData.FORMAT | CellData.NOTE)
```

## Method 1: read()

Read cells from specified ranges.

```python
def read(
    spreadsheet_id: str,
    ranges: List[str],
    types: int = CellData.VALUE
) -> dict
```

**Parameters:**

- `spreadsheet_id` - Spreadsheet ID (required)
- `ranges` - List of A1 notation ranges
  - `['Sheet1!A1:C10']` - Single range
  - `['Sheet1!A1:C10', 'Sheet2!B2:D5']` - Multiple ranges
  - `['Sheet1!A:A']` - Entire column
  - `['Sheet1!1:1']` - Entire row

- `types` - Bitmask of what to fetch (default: CellData.VALUE)
  - `CellData.VALUE` - Values only (fastest)
  - `CellData.FORMULA` - Show formulas as strings
  - `CellData.FORMAT` - Cell formatting
  - `CellData.NOTE` - Cell notes/comments
  - Combine with `|` operator

**Returns:**

Single range response:
```python
{
    'spreadsheetId': '...',
    'range': 'Sheet1!A1:C10',
    'values': [[1, 2, 3], [4, 5, 6], ...]
}
```

Multiple ranges response:
```python
{
    'spreadsheetId': '...',
    'valueRanges': [
        {'range': 'Sheet1!A1:C10', 'values': [...]},
        {'range': 'Sheet2!B2:D5', 'values': [...]}
    ]
}
```

With `FORMAT` or `NOTE` flags, returns grid data with full cell properties.

**Examples:**

```python
# Read values only (fastest)
data = client.read('spreadsheet-id', ['Sheet1!A1:C10'])
values = data.get('values', [])

# Read values and formulas
data = client.read(
    'spreadsheet-id',
    ['Sheet1!A1:C10'],
    types=CellData.VALUE | CellData.FORMULA
)

# Read everything
data = client.read(
    'spreadsheet-id',
    ['Sheet1!A1:C10'],
    types=CellData.VALUE | CellData.FORMULA | CellData.FORMAT | CellData.NOTE
)

# Read multiple ranges
data = client.read('spreadsheet-id', [
    'Sheet1!A1:C10',
    'Sheet2!B2:D5',
    'Summary!A1'
])
for value_range in data['valueRanges']:
    print(f"Range: {value_range['range']}")
    print(f"Values: {value_range.get('values', [])}")

# Read entire column
data = client.read('spreadsheet-id', ['Sheet1!A:A'])

# Read entire row
data = client.read('spreadsheet-id', ['Sheet1!1:1'])
```

**Notes:**
- Empty cells may be omitted from inner arrays
- Formulas only returned if `CellData.FORMULA` flag set
- `FORMAT`/`NOTE` require grid data (slower than values-only)
- Single range returns simpler response format
- Multiple ranges always return `valueRanges` list

## Method 2: write()

Write values, formatting, or notes to cells.

```python
def write(spreadsheet_id: str, data: List[dict]) -> dict
```

**Parameters:**

- `spreadsheet_id` - Spreadsheet ID (required)
- `data` - List of write operations

Each dict can have:
- `'range'` - A1 notation (required)
- `'values'` - 2D array for value/formula writes
- `'format'` - Format dict for formatting writes (not yet implemented)
- `'note'` - String for note writes (not yet implemented)

**Returns:**

```python
{
    'spreadsheetId': '...',
    'totalUpdatedRows': 10,
    'totalUpdatedColumns': 5,
    'totalUpdatedCells': 50,
    'responses': [...]
}
```

**Behavior:**
- Formulas starting with `=` are automatically parsed
- Clear values with `values=[[]]` or `values=[['']]`
- Multiple operations batched in single API call
- Values written in USER_ENTERED mode (formulas parsed)

**Examples:**

```python
# Write values
client.write('spreadsheet-id', [{
    'range': 'Sheet1!A1',
    'values': [[1, 2, 3], [4, 5, 6]]
}])

# Write formulas (parsed automatically)
client.write('spreadsheet-id', [{
    'range': 'Sheet1!D1',
    'values': [['=SUM(A1:C1)'], ['=SUM(A2:C2)']]
}])

# Write headers and data in one call
client.write('spreadsheet-id', [
    {'range': 'Sheet1!A1', 'values': [['Name', 'Age', 'Email']]},
    {'range': 'Sheet1!A2', 'values': [['Alice', 30, 'alice@example.com']]}
])

# Batch write multiple ranges
client.write('spreadsheet-id', [
    {'range': 'Sheet1!A1', 'values': [[1, 2, 3]]},
    {'range': 'Sheet2!B5', 'values': [[4, 5, 6]]},
    {'range': 'Sheet3!C10', 'values': [[7, 8, 9]]}
])

# Clear values
client.write('spreadsheet-id', [{
    'range': 'Sheet1!A1:C10',
    'values': [[]]
}])
```

**"Appending" Pattern:**

No special append mode. To append, find last row then write:

```python
# Read to find last row
data = client.read('spreadsheet-id', ['Sheet1!A:A'])
values = data.get('values', [])
last_row = len(values)

# Write to next row
client.write('spreadsheet-id', [{
    'range': f'Sheet1!A{last_row + 1}',
    'values': [[new_data]]
}])
```

**Notes:**
- Format and note writes not yet implemented (use `meta_write()` for formatting)
- All value writes use USER_ENTERED input mode
- Formulas must start with `=`
- Empty arrays clear values

## Method 3: meta_read()

Read spreadsheet metadata and structure without cell data.

```python
def meta_read(spreadsheet_id: str) -> dict
```

**Parameters:**
- `spreadsheet_id` - Spreadsheet ID (required)

**Returns:**

```python
{
    'spreadsheetId': '...',
    'properties': {
        'title': 'Spreadsheet Name',
        'locale': 'en_US',
        'timeZone': 'America/New_York'
    },
    'sheets': [
        {
            'properties': {
                'sheetId': 0,
                'title': 'Sheet1',
                'index': 0,
                'gridProperties': {
                    'rowCount': 1000,
                    'columnCount': 26,
                    'frozenRowCount': 0,
                    'frozenColumnCount': 0
                }
            }
        }
    ],
    'namedRanges': [...],
    'conditionalFormats': [...]
}
```

**Use Cases:**
- Get list of sheets
- Get sheet IDs (needed for `structure()` operations)
- Find named ranges
- Check frozen rows/columns
- Get sheet dimensions
- No cell data (fast operation)

**Examples:**

```python
# Get all sheets
meta = client.meta_read('spreadsheet-id')
for sheet in meta['sheets']:
    print(f"Sheet: {sheet['properties']['title']}")
    print(f"  ID: {sheet['properties']['sheetId']}")
    print(f"  Size: {sheet['properties']['gridProperties']}")

# Find sheet ID by name
meta = client.meta_read('spreadsheet-id')
sheet_id = next(
    s['properties']['sheetId']
    for s in meta['sheets']
    if s['properties']['title'] == 'Sales'
)

# List named ranges
meta = client.meta_read('spreadsheet-id')
for nr in meta.get('namedRanges', []):
    print(f"{nr['name']}: {nr['range']}")

# Check grid properties
meta = client.meta_read('spreadsheet-id')
grid = meta['sheets'][0]['properties']['gridProperties']
print(f"Rows: {grid['rowCount']}, Columns: {grid['columnCount']}")
```

**Notes:**
- Call this before `meta_write()` operations to get sheet IDs
- Fast operation - does not include cell data
- Returns complete spreadsheet structure

## Method 4: meta_write()

Write/modify spreadsheet metadata and structure using batch operations.

```python
def meta_write(spreadsheet_id: str, requests: List[dict]) -> dict
```

**Parameters:**

- `spreadsheet_id` - Spreadsheet ID (required)
- `requests` - List of request dicts (max 500 per call)

**Returns:**

```python
{
    'spreadsheetId': '...',
    'replies': [...]  # One reply per request
}
```

**Common Request Types:**

### Sheet Operations
- `addSheet` - Create new sheet
- `deleteSheet` - Delete sheet
- `updateSheetProperties` - Modify sheet properties

### Dimension Operations
- `insertDimension` - Insert rows/columns
- `deleteDimension` - Delete rows/columns
- `updateDimensionProperties` - Resize, hide/show
- `autoResizeDimensions` - Auto-fit column widths

### Formatting
- `repeatCell` - Apply format to range
- `updateCells` - Write values with format
- `mergeCells` / `unmergeCells` - Merge/unmerge cells
- `updateBorders` - Add borders

### Rules
- `addConditionalFormatRule` / `deleteConditionalFormatRule`
- `addNamedRange` / `deleteNamedRange`
- `addProtectedRange` / `deleteProtectedRange`

### Other Operations
- `findReplace` - Find and replace
- `sortRange` - Sort data
- `copyPaste` / `cutPaste` - Copy/move ranges

Full list: [Google Sheets API Request Types](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request)

**Examples:**

### Create New Sheet

```python
client.meta_write('spreadsheet-id', [{
    'addSheet': {
        'properties': {
            'title': 'Sales Data',
            'gridProperties': {
                'rowCount': 100,
                'columnCount': 10
            }
        }
    }
}])
```

### Freeze Rows

```python
# Get sheet ID first
meta = client.meta_read('spreadsheet-id')
sheet_id = meta['sheets'][0]['properties']['sheetId']

client.meta_write('spreadsheet-id', [{
    'updateSheetProperties': {
        'properties': {
            'sheetId': sheet_id,
            'gridProperties': {'frozenRowCount': 1}
        },
        'fields': 'gridProperties.frozenRowCount'
    }
}])
```

### Format Header Row

```python
client.meta_write('spreadsheet-id', [{
    'repeatCell': {
        'range': {
            'sheetId': sheet_id,
            'startRowIndex': 0,
            'endRowIndex': 1
        },
        'cell': {
            'userEnteredFormat': {
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                'textFormat': {'bold': True}
            }
        },
        'fields': 'userEnteredFormat(backgroundColor,textFormat)'
    }
}])
```

### Auto-Resize Columns

```python
client.meta_write('spreadsheet-id', [{
    'autoResizeDimensions': {
        'dimensions': {
            'sheetId': sheet_id,
            'dimension': 'COLUMNS',
            'startIndex': 0,
            'endIndex': 10
        }
    }
}])
```

### Add Borders

```python
client.meta_write('spreadsheet-id', [{
    'updateBorders': {
        'range': {
            'sheetId': sheet_id,
            'startRowIndex': 0,
            'endRowIndex': 10,
            'startColumnIndex': 0,
            'endColumnIndex': 5
        },
        'top': {'style': 'SOLID', 'width': 1},
        'bottom': {'style': 'SOLID', 'width': 1},
        'left': {'style': 'SOLID', 'width': 1},
        'right': {'style': 'SOLID', 'width': 1},
        'innerHorizontal': {'style': 'SOLID', 'width': 1},
        'innerVertical': {'style': 'SOLID', 'width': 1}
    }
}])
```

### Conditional Formatting

```python
client.meta_write('spreadsheet-id', [{
    'addConditionalFormatRule': {
        'rule': {
            'ranges': [{
                'sheetId': sheet_id,
                'startRowIndex': 1,
                'endRowIndex': 100,
                'startColumnIndex': 2,
                'endColumnIndex': 3
            }],
            'booleanRule': {
                'condition': {
                    'type': 'NUMBER_GREATER',
                    'values': [{'userEnteredValue': '100'}]
                },
                'format': {
                    'backgroundColor': {'red': 0.9, 'green': 1.0, 'blue': 0.9}
                }
            }
        },
        'index': 0
    }
}])
```

### Batch Multiple Operations

```python
# Combine multiple operations in one call
client.meta_write('spreadsheet-id', [
    # Create sheet
    {'addSheet': {'properties': {'title': 'Dashboard'}}},

    # Freeze header row
    {
        'updateSheetProperties': {
            'properties': {
                'sheetId': sheet_id,
                'gridProperties': {'frozenRowCount': 1}
            },
            'fields': 'gridProperties.frozenRowCount'
        }
    },

    # Auto-resize columns
    {
        'autoResizeDimensions': {
            'dimensions': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'startIndex': 0,
                'endIndex': 5
            }
        }
    }
])
```

**Notes:**
- Maximum 500 requests per call
- Operations execute in order
- Get sheet IDs from `meta_read()` first
- Use `fields` parameter to specify what to update
- `replies` array contains results for each request

## Utility Functions

### column_to_index()

Convert column letter(s) to zero-based index.

```python
from sheet_client import column_to_index

column_to_index('A')    # 0
column_to_index('B')    # 1
column_to_index('Z')    # 25
column_to_index('AA')   # 26
column_to_index('AB')   # 27
```

### index_to_column()

Convert zero-based index to column letter(s).

```python
from sheet_client import index_to_column

index_to_column(0)    # 'A'
index_to_column(1)    # 'B'
index_to_column(25)   # 'Z'
index_to_column(26)   # 'AA'
index_to_column(27)   # 'AB'
```

### a1_to_grid_range()

Convert A1 notation to GridRange format for batch operations.

```python
from sheet_client import a1_to_grid_range

result = a1_to_grid_range('A1:C10', sheet_id=0)
# Returns:
# {
#     'sheetId': 0,
#     'startRowIndex': 0,      # Inclusive, zero-based
#     'endRowIndex': 10,       # Exclusive
#     'startColumnIndex': 0,   # Inclusive, zero-based
#     'endColumnIndex': 3      # Exclusive
# }

# Sheet name in A1 notation is ignored
a1_to_grid_range('Sheet1!A1:C10', sheet_id=5)  # Uses sheet_id=5

# Single cell
a1_to_grid_range('B5:B5', sheet_id=0)
```

## Key Concepts

### A1 Notation

Range specification format:

- `'Sheet1!A1:C10'` - Range with sheet name
- `'Sheet1!A1'` - Single cell
- `'Sheet1!A:A'` - Entire column
- `'Sheet1!1:1'` - Entire row
- `'Sheet1!A:C'` - Multiple columns
- `'Sheet1!1:5'` - Multiple rows

Always include sheet name when using API methods.

### GridRange

Low-level range format for `structure()` operations:

```python
{
    'sheetId': 0,              # Get from metadata()
    'startRowIndex': 0,        # Zero-based, inclusive
    'endRowIndex': 10,         # Zero-based, exclusive (Python slicing)
    'startColumnIndex': 0,     # Zero-based, inclusive
    'endColumnIndex': 3        # Zero-based, exclusive
}
```

**Important:** End indices are exclusive (Python slice semantics).

Example - first row only:
```python
{'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1}
```

### Sheet IDs

Every sheet has an integer ID:
- Get from `metadata()`: `data['sheets'][i]['properties']['sheetId']`
- Required for all GridRange operations in `structure()`
- Usually 0 for first sheet, but not guaranteed

### Color Format

RGB values as floats from 0.0 to 1.0:

```python
{'red': 1.0, 'green': 0.5, 'blue': 0.0}
```

Common colors:
```python
# White
{'red': 1.0, 'green': 1.0, 'blue': 1.0}

# Black
{'red': 0.0, 'green': 0.0, 'blue': 0.0}

# Light gray
{'red': 0.9, 'green': 0.9, 'blue': 0.9}

# Light green
{'red': 0.85, 'green': 1.0, 'blue': 0.85}

# Light red
{'red': 1.0, 'green': 0.85, 'blue': 0.85}
```

### Number Formats

Apply via `repeatCell` in `structure()`:

```python
{
    'numberFormat': {
        'type': 'CURRENCY',
        'pattern': '$#,##0.00'
    }
}
```

Common types: `NUMBER`, `CURRENCY`, `PERCENT`, `DATE`, `TIME`, `DATE_TIME`

## Error Handling

### Exceptions

```python
from sheet_client import (
    SheetsAPIError,
    AuthenticationError,
    RateLimitError,
    ServerError
)
```

**AuthenticationError** - OAuth failed
- Token expired or invalid
- Credentials file missing
- User denied access

**RateLimitError** - Rate limit exceeded (429)
- Automatically retried with exponential backoff
- Raised if still failing after retries

**ServerError** - Google API server error (500, 503)
- Automatically retried with exponential backoff
- Raised if still failing after retries

**SheetsAPIError** - Other API errors (400, 404, etc.)
- Invalid spreadsheet ID
- Invalid range format
- Permission denied

### Automatic Retries

Client automatically retries:
- **429 (Rate Limit)**: 3 attempts, exponential backoff (1s, 2s, 4s)
- **500, 503 (Server Error)**: 3 attempts, exponential backoff

No manual retry logic needed.

### Error Handling Example

```python
try:
    client.write([{'range': 'Sheet1!A1', 'values': [[1, 2, 3]]}])
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
except SheetsAPIError as e:
    print(f"API error (status {e.status_code}): {e}")
```

## API Quotas

Google Sheets API v4 limits:

- 100 requests per second per user (read/write)
- 500 requests maximum per batch operation
- 5 million cells maximum per spreadsheet
- Unlimited daily quota for OAuth users

**Tips:**
- Use batch operations to minimize API calls
- Each batch operation counts as 1 API call
- Multiple ranges in `read()` counts as 1 call
- Multiple operations in `meta_write()` counts as 1 call

## Complete Examples

### Example 1: Read and Analyze

```python
from sheet_client import SheetsClient, CellData

client = SheetsClient()

# Get structure
meta = client.meta_read('your-spreadsheet-id')
print(f"Sheets: {[s['properties']['title'] for s in meta['sheets']]}")

# Read values
data = client.read('your-spreadsheet-id', ['Sheet1!A1:C10'])
values = data.get('values', [])
for row in values:
    print(row)
```

### Example 2: Create Formatted Table

```python
# Get sheet ID
meta = client.meta_read('your-spreadsheet-id')
sheet_id = meta['sheets'][0]['properties']['sheetId']

# Write data
client.write('your-spreadsheet-id', [
    {'range': 'Sheet1!A1', 'values': [['Name', 'Department', 'Salary']]},
    {'range': 'Sheet1!A2', 'values': [
        ['Alice', 'Engineering', 120000],
        ['Bob', 'Marketing', 90000],
        ['Charlie', 'Sales', 110000]
    ]}
])

# Format
client.meta_write('your-spreadsheet-id', [
    # Header format
    {
        'repeatCell': {
            'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1},
            'cell': {'userEnteredFormat': {
                'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2},
                'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
            }},
            'fields': 'userEnteredFormat'
        }
    },
    # Freeze header
    {
        'updateSheetProperties': {
            'properties': {'sheetId': sheet_id, 'gridProperties': {'frozenRowCount': 1}},
            'fields': 'gridProperties.frozenRowCount'
        }
    },
    # Currency format
    {
        'repeatCell': {
            'range': {'sheetId': sheet_id, 'startRowIndex': 1, 'endRowIndex': 4, 'startColumnIndex': 2, 'endColumnIndex': 3},
            'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0'}}},
            'fields': 'userEnteredFormat.numberFormat'
        }
    },
    # Auto-resize
    {
        'autoResizeDimensions': {
            'dimensions': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 3}
        }
    }
])
```

### Example 3: Find Formulas

```python
# Read with grid data
data = client.read('your-spreadsheet-id', ['Sheet1!A1:Z100'], types=CellData.VALUE | CellData.FORMAT)

if 'sheets' in data:
    for sheet in data['sheets']:
        if 'data' not in sheet:
            continue

        for row_idx, row in enumerate(sheet['data'][0].get('rowData', [])):
            for col_idx, cell in enumerate(row.get('values', [])):
                if 'userEnteredValue' in cell:
                    uev = cell['userEnteredValue']
                    if 'formulaValue' in uev:
                        print(f"Formula at [{row_idx},{col_idx}]: {uev['formulaValue']}")
```

## See Also

- [Google Sheets API v4 Documentation](https://developers.google.com/sheets/api)
- [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- Example scripts in `example/` directory
- CLAUDE.md for Claude Code usage patterns
