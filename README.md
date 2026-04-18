# Google Sheets CLI

Minimal Python wrapper for Google Sheets REST API v4. Provides direct access to the Google Sheets API with OAuth 2.0 authentication.

**MCP Server Available**: A Model Context Protocol (MCP) server is included for use with Claude Desktop and other MCP clients. See [mcp-server/README.md](mcp-server/README.md) for details.

## Description

This package wraps the Google Sheets API v4 with minimal abstraction. All methods return raw Google API responses, providing authenticated access to discovery, read, write, and batch operations.

The design provides no higher-level abstractions, helper functions, or opinionated interfaces. Users access the Google Sheets API directly through thin wrapper methods that handle authentication and retry logic.

## Architecture

**Core components:**
- SheetsClient: Main class providing API method wrappers
- OAuth 2.0 authentication with token caching
- Automatic retry logic for rate limits (429) and server errors (500, 503)
- Utility functions for A1 notation conversion

**What this provides:**
- Discovery: `meta_read()` returns complete spreadsheet state
- Read: Value retrieval with rendering options (values, formulas, formatting, notes)
- Write: Batched value writes via `write()` and `clear()`
- Batch: Direct access to `meta_write()` (spreadsheets.batchUpdate) for structural/formatting operations
- Authentication: OAuth flow with token persistence

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
4. Download credentials as `~/.sheet-cli/credentials.json`

## Authentication

First run initiates OAuth flow:
```bash
python your_script.py
```
Browser opens for user authorization. Token cached to `~/.sheet-cli/token.json` for subsequent runs. Token auto-refreshes when expired.

**Credential Storage**: All credentials are stored in `~/.sheet-cli/` with secure permissions (directory: 700, files: 600).

## CLI Usage

The CLI exposes six verbs over a unified target grammar:

```
sheet-cli get    TARGET            read cell / range / sheet / spreadsheet / drive
sheet-cli put    TARGET [VALUE]    write cells (scalar sugar or stdin)
sheet-cli del    TARGET            clear range / delete sheet / row / col / spreadsheet
sheet-cli new    [TARGET]          create spreadsheet / sheet / row / col
sheet-cli copy   SOURCE DEST       copy (server-side when possible)
sheet-cli move   SOURCE DEST       move (server-side when possible)
sheet-cli auth                     run OAuth flow
```

### Target grammar

```
SID                       whole spreadsheet
SID:Sheet                 a sheet
SID:Sheet!A1:B10          a range within a sheet
SID:Sheet!A1              a single cell
SID:Sheet!5               row 5 of the sheet
SID:Sheet!C               column C of the sheet
SID:!A1                   range in the first/default sheet
```

For the second operand of `copy` / `move`, any part may be omitted and
inherited from the first operand:

```
Sheet!A1                  inherit SID, use Sheet + A1
!A1                       inherit SID AND sheet, use A1
:Sheet                    inherit SID, sheet-level target
```

### Properties (`.property` suffix)

Any target may carry a trailing `.property` to address formatting,
structure, or metadata of the resource. The same six verbs apply:

```
SID.title                  spreadsheet title
SID.named.sales            a named range (keyed by name)
SID:Sheet.freeze           frozen rows / columns
SID:Sheet.color            tab color
SID:Sheet.hidden           visibility
SID:Sheet.conditional[0]   conditional-format rule by index
SID:Sheet!A1:B2.format     cell format for a range
SID:Sheet!A1:B2.borders    borders
SID:Sheet!A1:B2.merge      merges
SID:Sheet!A1:B2.note       notes
SID:Sheet!A1:B2.validation data validation
SID:Sheet!A1:B2.protected  protected range
SID:Sheet!5.height         row pixel height
SID:Sheet!C.width          column pixel width
```

`copy` and `move` do not accept `.property` targets. Scalar sugar works
for simple properties (`put .freeze "2 1"`, `put .color "#ff00aa"`,
`put .title "New"`); structured request bodies come from stdin as JSON.

### Examples

```bash
# List spreadsheets in Drive
sheet-cli get

# Full spreadsheet metadata
sheet-cli get SID

# A single cell (text output; use --format=json for raw API shape)
sheet-cli get SID:Sheet1!A1

# Scalar write (sugar)
sheet-cli put SID:Sheet1!A1 "hello world"

# Batch write from stdin (JSON or cell-value text — auto-detected)
echo '{"A1": "hello", "B1": 42}' | sheet-cli put SID:Sheet1

# Clear a range / delete a row / delete a sheet
sheet-cli del SID:Sheet1!A1:C10
sheet-cli del SID:Sheet1!5
sheet-cli del SID:Sheet1

# Create
sheet-cli new "My New Spreadsheet"        # prints new SID
sheet-cli new SID:NewSheet                # add a sheet
sheet-cli new SID:Sheet1!5 --side=above   # insert a row

# Copy a range within the same spreadsheet (server-side)
sheet-cli copy SID:Sheet1!A1:B10 :Sheet2!D1

# Copy a whole sheet across spreadsheets (server-side via sheets.copyTo)
sheet-cli copy SID1:Sheet1 SID2

# Move a row
sheet-cli move SID:Sheet1!5 !2

# Properties
sheet-cli put SID.title "Q3 Report"
sheet-cli put SID:Sheet1.freeze "2 1"
sheet-cli put SID:Sheet1.color "#ffcc00"
echo '{"backgroundColor":{"red":1.0}}' | sheet-cli put SID:Sheet1!A1:B2.format
sheet-cli put SID.named.sales "Sheet1!A1:B100"
sheet-cli get SID:Sheet1.conditional
```

### Output rules

- `get` prints cell/value text by default; `--format=json` emits the raw API response.
- Mutations (`put`, `del`, `copy`, `move`) are silent by default; `--format=json` echoes the target and response.
- `new` always emits JSON (the new SID / sheet properties are the point).

## API Methods

Complete API reference in API.md:
- `SheetsClient.__init__(credentials_path=None, token_path=None)` - Initialize with OAuth
- `read(spreadsheet_id, ranges, types=CellData.VALUE)` - Read cells (supports VALUE / FORMULA / FORMAT / NOTE flags)
- `write(spreadsheet_id, data)` - Batch value writes (list of `{range, values}` dicts)
- `clear(spreadsheet_id, ranges)` - Clear cell values in one or more ranges
- `meta_read(spreadsheet_id)` - Read spreadsheet metadata/structure
- `meta_write(spreadsheet_id, requests)` - Raw batchUpdate for formatting/structure
- `create(title, sheets=None)` - Create a new spreadsheet
- `copy_sheet_to(source_id, source_sheet_id, dest_id)` - Server-side sheet copy between spreadsheets
- `delete_spreadsheet(spreadsheet_id)` - Delete a spreadsheet via Drive API
- `list_spreadsheets(include_shared_drives=False)` - List spreadsheets via Drive API

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
Integer identifiers for sheets (not the same as sheet names). Required for GridRange operations. Retrieved from `meta_read()`.

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
│   ├── sheet_client/         # Library (Python API)
│   │   ├── client.py         # SheetsClient
│   │   ├── auth.py           # OAuth flow
│   │   ├── utils.py          # A1 notation utilities
│   │   ├── exceptions.py     # Custom exceptions
│   │   └── __init__.py       # Package exports
│   └── sheet_cli/            # CLI layer
│       ├── cli.py            # Six-verb argparse entry point
│       ├── grammar.py        # Target-string grammar (parse/resolve/classify)
│       ├── properties.py     # Property handler registry (.format, .freeze, …)
│       ├── verbs.py          # get / put / del / new dispatch
│       ├── dispatch.py       # copy / move with server-side optimizations
│       ├── formats.py        # stdin/stdout formatters
│       └── __main__.py       # `python -m sheet_cli`
├── mcp-server/               # MCP server exposing client to Claude Desktop
├── example/                  # Usage examples
├── test/                     # Unit, mock, and integration tests
├── API.md                    # Complete API reference
├── CLAUDE.md                 # Claude Code guidance
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── requirements-dev.txt      # Dev dependencies (pytest)
└── .gitignore                # Excludes credentials, tokens
```

## Documentation

- **llms.txt** - Concise agent-facing reference (grammar, dispatch table, bulk-write patterns)
- **API.md** - Complete technical reference with method signatures, parameters, return values, and code examples
- **CLAUDE.md** - Guidance for Claude Code usage patterns
- **TESTING.md** - Test layout and how to run the suite
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
