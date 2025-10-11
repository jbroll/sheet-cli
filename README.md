# Google Sheets CLI

Minimal Python wrapper for Google Sheets REST API v4. Provides direct access to the Google Sheets API with OAuth 2.0 authentication.

## Description

This package wraps the Google Sheets API v4 with minimal abstraction. All methods return raw Google API responses. The implementation consists of approximately 300 lines of Python code providing authenticated access to discovery, read, write, and batch operations.

The design provides no higher-level abstractions, helper functions, or opinionated interfaces. Users access the Google Sheets API directly through thin wrapper methods that handle authentication and retry logic.

## Architecture

**Core components:**
- SheetsClient: Main class providing API method wrappers
- OAuth 2.0 authentication with token caching
- Automatic retry logic for rate limits (429) and server errors (500, 503)
- Utility functions for A1 notation conversion

**What this provides:**
- Discovery: `get_spreadsheet()` returns complete spreadsheet state
- Read: Value retrieval methods with rendering options
- Write: Value write and append operations
- Batch: Direct access to `batch_update()` for structural/formatting operations
- Authentication: OAuth flow with token persistence

**What this does not provide:**
- No table creation helpers
- No theme system
- No formula parsing
- No structural analysis
- No template system
- No data transformation
- No validation logic

## Requirements

- Python 3.8+
- Google Cloud project with Sheets API enabled
- OAuth 2.0 Client ID credentials

**Python dependencies:**
```
google-api-python-client>=2.0.0
google-auth>=2.0.0
google-auth-oauthlib>=0.5.0
google-auth-httplib2>=0.1.0
```

## Installation

Install dependencies:
```bash
pip install -r requirements.txt
```

Set up OAuth credentials:
1. Create project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable Google Sheets API
3. Create OAuth 2.0 Client ID (Desktop application type)
4. Download credentials as `credentials.json` in project root

## Authentication

First run initiates OAuth flow:
```bash
python your_script.py
```
Browser opens for user authorization. Token cached to `token.pickle` for subsequent runs. Token auto-refreshes when expired.

## Usage

### Basic Operations

Initialize client with spreadsheet ID from URL:
```bash
# Spreadsheet URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit
# Use SPREADSHEET_ID in code
```

Read spreadsheet structure:
```bash
# Returns sheet names, IDs, properties, optionally cell data
```

Read cell values:
```bash
# Specify range in A1 notation: Sheet1!A1:C10
# Returns 2D list of values
```

Write cell values:
```bash
# Specify starting cell and 2D value array
# Formulas parsed when using USER_ENTERED mode
```

Append to sheet:
```bash
# Appends after last row with data in specified column range
```

### Batch Operations

Format cells:
```bash
# Apply colors, fonts, alignment, borders to ranges
# Use repeatCell request type
```

Modify structure:
```bash
# Freeze rows/columns with updateSheetProperties
# Add/delete sheets with addSheet/deleteSheet
# Insert/delete rows/columns with insertDimension/deleteDimension
```

Auto-resize columns:
```bash
# Automatically adjust column widths to fit content
```

Conditional formatting:
```bash
# Add rules with conditions and formatting
# Types: number comparisons, text matches, custom formulas
```

### Advanced Features

Multiple range reads:
```bash
# Read from multiple ranges in single API call
# Returns dict with valueRanges list
```

Formula handling:
```bash
# Write: Formulas (starting with =) parsed in USER_ENTERED mode
# Read: Use FORMULA value_render to get formula strings
```

Merge cells:
```bash
# Merge ranges using mergeCells request
# Unmerge with unmergeCells request
```

## API Methods

Complete API reference in API.md:
- `SheetsClient.__init__()` - Initialize with OAuth
- `get_spreadsheet()` - Discovery method
- `read_values()` - Single range read
- `batch_get_values()` - Multiple range read
- `write_values()` - Overwrite range
- `append_values()` - Append after data
- `clear_values()` - Clear range
- `batch_update_values()` - Multiple range write
- `batch_update()` - Structural/formatting operations

Utility functions:
- `column_to_index()` - Convert column letters to indices
- `index_to_column()` - Convert indices to column letters
- `a1_to_grid_range()` - Convert A1 notation to GridRange

## Key Concepts

**A1 Notation:**
Range specification format. Examples: `Sheet1!A1:C10`, `Sheet1!A:A`, `Sheet1!1:1`

**GridRange:**
Low-level range format using zero-based indices with exclusive end values (Python slice semantics). Used in batch operations.

**Sheet IDs:**
Integer identifiers for sheets (not the same as sheet names). Required for GridRange operations. Retrieved from `get_spreadsheet()`.

**Value Rendering:**
Options for how values are returned: FORMATTED_VALUE (default), UNFORMATTED_VALUE, FORMULA.

**Input Options:**
USER_ENTERED (parse formulas/dates) vs RAW (literal text).

## Error Handling

**Automatic retries:**
- Rate limits (429): 3 attempts with exponential backoff
- Server errors (500, 503): 3 attempts with exponential backoff

**Exceptions:**
- `AuthenticationError` - OAuth failure
- `RateLimitError` - Rate limit after retries
- `ServerError` - Server error after retries
- `SheetsAPIError` - Other API errors (400, 404, etc.)

All exceptions include status codes and error details from API response.

## API Quotas

Google Sheets API v4 limits:
- 100 requests per second per user (read/write)
- 500 requests maximum per batch operation
- 5 million cells maximum per spreadsheet
- Unlimited daily quota for OAuth users

Use batch operations to minimize API call count.

## Examples

Example scripts in `example/` directory:
- `01_basic_operations.py` - Read/write operations with formulas
- `02_batch_formatting.py` - Create formatted table with colors, borders, frozen rows
- `03_discovery_analysis.py` - Analyze spreadsheet structure and find formulas

Run examples:
```bash
# Edit example file to add spreadsheet ID
# Run with Python
python example/01_basic_operations.py
```

## Testing

Unit tests in `test/` directory:
```bash
# Run tests with pytest
pytest test/test_client.py -v
```

Tests cover:
- A1 notation conversion utilities
- Column index conversion (round-trip)
- GridRange generation
- Exception behavior

Integration tests require real spreadsheet and are optional.

## File Structure

```
sheet-cli/
├── src/
│   ├── client.py         # SheetsClient implementation
│   ├── auth.py           # OAuth flow
│   ├── utils.py          # A1 notation utilities
│   ├── exceptions.py     # Custom exceptions
│   └── __init__.py       # Package exports
├── example/              # Usage examples
├── test/                 # Unit tests
├── API.md                # Complete API reference
├── CLAUDE.md             # Claude Code guidance
├── README.md             # This file
├── requirements.txt      # Python dependencies
└── .gitignore           # Excludes credentials, tokens
```

## Documentation

- **API.md** - Complete technical reference with method signatures, parameters, return values, and code examples
- **CLAUDE.md** - Guidance for Claude Code usage patterns
- **Google Sheets API v4** - [Official documentation](https://developers.google.com/sheets/api)
- **OAuth 2.0** - [Desktop app flow](https://developers.google.com/identity/protocols/oauth2/native-app)

## Design Rationale

This wrapper provides minimal abstraction over the Google Sheets API. All methods return raw API responses without transformation. This design allows:

- Direct access to all API response fields
- No learning curve beyond Google's API documentation
- Easy debugging with raw API responses
- Flexibility to use any API feature
- Composition of operations based on specific needs

The tradeoff is lack of convenience helpers. Users must compose operations from API primitives and handle raw response structures.

## License

MIT
