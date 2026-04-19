# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Project Context

**Google Sheets CLI** - Minimal Python wrapper for Google Sheets REST API v4. Provides direct API access with OAuth 2.0 authentication.

**Status**: Implemented and ready for use.

## Philosophy

No opinions, just access. Direct mapping to Google's REST API with minimal abstraction.

**What this provides:**
- Discovery: Get complete spreadsheet state
- Read/Write: Direct value operations
- Batch: Full access to API batch operations
- OAuth: User authentication with token caching

**What this doesn't provide:**
- No helper functions like "create_table()"
- No theme system
- No formula parsing or analysis
- No structural analysis
- No pre-built templates

**Why**: You compose operations from raw API primitives based on user needs. No fighting with abstractions.

## Technology Stack

- Python 3.8+
- Google Sheets REST API v4 (direct)
- OAuth 2.0 (sheet owner model)
- Dependencies: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`

## File Structure

```
sheet-cli/
├── src/
│   ├── sheet_client/     # Library (thin Google API wrapper)
│   │   ├── client.py     # SheetsClient
│   │   ├── auth.py       # OAuth flow
│   │   ├── utils.py      # A1/grid utilities
│   │   └── exceptions.py # Custom exceptions
│   └── sheet_cli/        # Unified six-verb CLI
│       ├── cli.py        # argparse entry point
│       ├── grammar.py    # target-string grammar (parse/resolve/classify)
│       ├── verbs.py      # get / put / del / new
│       ├── dispatch.py   # copy / move with server-side optimizations
│       ├── properties.py # property handlers (.format, .freeze, .named, …)
│       └── formats.py    # stdin/stdout formatters
│
├── mcp-server/           # MCP server exposing client to Claude Desktop
├── example/              # Usage examples
├── test/                 # Unit tests
├── API.md                # Complete API reference
├── README.md             # User documentation
└── CLAUDE.md             # This file
```

## CLI Grammar (v2)

Six verbs over one target-string grammar:

```
get    TARGET            read cell / range / sheet / spreadsheet / drive
put    TARGET [VALUE]    write; scalar sugar, else auto-detected stdin
del    TARGET            clear range / delete sheet / row / col / spreadsheet
new    [TARGET]          create spreadsheet / sheet / row / col
copy   SOURCE DEST       copy (server-side when possible)
move   SOURCE DEST       move (server-side when possible)
```

Target syntax: `SID:Sheet!locator`. Second-operand parts can be omitted to
inherit from the first (e.g., `:Sheet2!A1` for same SID, different sheet).
Output: `get` is text-first (use `--format=json` for API shape); mutations
are silent (use `--format=json` to echo); `new` always prints JSON.

### Properties — `TARGET.property`

Any target may carry a `.property` suffix to address formatting, structure,
or metadata of the resource. The same six verbs apply; property responses
are always JSON. Collection elements are addressed by name (`named.NAME`)
or index (`conditional[0]`).

| Scope | Properties |
|---|---|
| spreadsheet | `title`, `named.NAME`, `parents` / `parents.FOLDER_ID` |
| sheet | `title`, `freeze`, `color`, `hidden`, `conditional[i]` |
| range | `format`, `borders`, `merge`, `note`, `validation`, `protected` |
| row | `height` |
| column | `width` |

Scalar sugar: `put .freeze "2 1"`, `put .color "#ff00aa"`, `put .title "New"`,
`put .named.sales "Sheet1!A1:B100"`, `put .parents FOLDER_ID`. Structured
bodies (format, borders, validation, conditional rules) come from stdin as
JSON matching the corresponding Sheets API request type. `copy` / `move`
do not accept `.property` targets.

`.parents` is the only property that routes through the Drive API —
everything else is pure Sheets API. Use it to inspect or change which
Drive folder(s) contain a spreadsheet (`get/put/new/del SID.parents[.FID]`).

Whole-spreadsheet copy (`copy SID "Title"` or `copy SID ""`) routes
through Drive `files.copy` — the destination SID slot is interpreted as
the new file's title, or DRIVE for a default `"Copy of …"` name.

## How You Use This

### Pattern 1: Always Discover First

Before making changes, get the complete state:
- Use `meta_read()` to understand structure
- Analyze raw API response to check for existing data
- Get sheet IDs needed for batch operations
- Make informed decisions based on current state

### Pattern 2: Compose Batch Operations

When user requests complex operations:
- Break into discrete API operations
- Use batch operations for formatting/structure
- Compose exactly what's needed from raw request types
- No pre-built helpers - compose fresh each time

### Pattern 3: Work with Raw API Responses

- All methods return raw Google API responses
- No parsing layers or custom data structures
- Analyze responses directly using Python
- Access any field Google provides

## Common Workflows

**Creating formatted tables:**
1. Get sheet ID from discovery
2. Write data with value operations
3. Apply formatting with batch operations
4. Use auto-resize, freeze rows, etc.

**Finding formulas:**
1. Get spreadsheet with grid data
2. Iterate through row data
3. Check cells for 'formulaValue' in 'userEnteredValue'
4. Process as needed

**Smart append vs write:**
1. Check if sheet has existing data
2. Append if data exists, write if empty
3. No magic - explicit decisions

**Bulk cell operations with Python generation:**
When writing many cells (hundreds or thousands), generate JSON data with Python and
pipe to `sheet-cli put SID:Sheet`. Keys in the JSON are A1 addresses relative to the
target sheet (no `Sheet1!` prefix needed — it's inherited from the target).

```bash
# Use Write tool to create /tmp/gen.py, then execute:
python3 /tmp/gen.py | venv/bin/sheet-cli put SPREADSHEET_ID:Sheet1
```

`/tmp/gen.py`:
```python
import json
data = {}
for row in range(10, 47):
    data[f"A{row}"] = f"=SUM(B{row}:D{row})"
    data[f"E{row}"] = f"=A{row}*0.027"
print(json.dumps(data, indent=2))
```

This scales from dozens to thousands of cells in a single API call. Use it for:
- Creating new sheets with structured data
- Applying formulas to many rows
- Any operation on 10+ cells

Prefer the Write tool for generating the script (avoids heredoc approval prompts).

## Implementation Notes

**Error Handling:**
- Automatic retry on 429 (rate limit) with exponential backoff
- Automatic retry on 500, 503 (server errors)
- Clear exceptions with status codes

**Authentication:**
- OAuth flow opens browser on first run
- Token cached as JSON at `~/.sheet-cli/token.json`, auto-refreshes
- User grants access to their own sheets

**Type Hints:**
- All public methods have type hints
- Return types: `dict` (raw API) or `List[List[Any]]` (values)

## API Reference

See API.md for complete technical reference including:
- All method signatures
- Request/response formats
- GridRange specifications
- A1 notation details
- Batch operation types
- Code examples

## Testing

Unit tests focus on:
- A1 notation conversion utilities
- Exception handling
- Round-trip conversions

Integration tests optional (require real spreadsheet).

## Google API Resources

When you need to compose operations, refer to:
- [spreadsheets.get](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/get)
- [spreadsheets.values](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values)
- [spreadsheets.batchUpdate](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)
- [Request types](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request)

## Why This Design

**For you (Claude):**
- Raw API responses to analyze directly
- No abstractions to learn or work around
- Direct mapping to Google's documentation
- Compose exactly what each task needs

**For implementation:**
- Minimal code (~300 lines)
- No state management complexity
- No custom data structures
- Easy to maintain

**For users:**
- Direct API control
- Full Google Sheets API power
- No magic behavior
- Easy debugging with raw responses

## Summary

This is a thin wrapper providing authenticated access to Google Sheets REST API v4. Discovery, read, write, and batch operations. Everything else is composition.
