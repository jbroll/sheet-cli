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
│   ├── sheet_cli/        # Unified verb CLI
│   │   ├── multicall.py  # multi-call launcher (dispatch on argv[0])
│   │   ├── cli.py        # argparse entry point
│   │   ├── grammar.py    # target-string grammar (parse/resolve/classify)
│   │   ├── verbs.py      # get / put / del / new
│   │   ├── dispatch.py   # copy / move with server-side optimizations
│   │   ├── properties.py # property handlers (.format, .freeze, .named, …)
│   │   ├── builders.py   # pure batchUpdate request builders (shared with batch)
│   │   ├── batch.py      # batch verb core (ops list → values + requests)
│   │   └── formats.py    # stdin/stdout formatters
│   └── drive_cli/        # Drive-native CLI (IDs, not the target grammar)
│       ├── cli.py        # argparse entry point
│       ├── ops.py        # shared verb core (also used by the MCP server)
│       └── transfer.py   # ownership transfer across a folder tree
│
├── mcp-server/           # MCP server exposing client to Claude Desktop
├── example/              # Usage examples
├── test/                 # Unit tests
├── API.md                # Complete API reference
├── README.md             # User documentation
└── CLAUDE.md             # This file
```

## CLI Grammar (v2)

Verbs over one target-string grammar (the six original verbs plus `batch`):

```
get    TARGET            read cell / range / sheet / spreadsheet / drive
put    TARGET [VALUE]    write; scalar sugar, else auto-detected stdin
del    TARGET            clear range / delete sheet / row / col / spreadsheet
new    [TARGET]          create spreadsheet / sheet / row / col
copy   SOURCE DEST       copy (server-side when possible)
move   SOURCE DEST       move (server-side when possible)
batch  SID --file ops.json  apply a JSON list of operations in one call
```

Target syntax: `SID:Sheet!locator`. Second-operand parts can be omitted to
inherit from the first (e.g., `:Sheet2!A1` for same SID, different sheet).
Output: `get` is text-first (use `--format=json` for API shape); mutations
are silent (use `--format=json` to echo); `new` always prints JSON.
`get --render formula|formatted|unformatted` maps to `valueRenderOption`
for cell reads; the default `formula` shows formulas, the others computed values.

### Properties — `TARGET.property`

Any target may carry a `.property` suffix to address formatting, structure,
or metadata of the resource. The same verbs apply; property responses
are always JSON. Collection elements are addressed by name (`named.NAME`)
or index (`conditional[0]`).

| Scope | Properties |
|---|---|
| spreadsheet | `title`, `locale`, `timeZone`, `autoRecalc`, `theme`, `defaultFormat`, `iterativeCalc`, `named.NAME`, `parents` / `parents.FOLDER_ID` |
| sheet | `title`, `index`, `freeze`, `color`, `hidden`, `hideGridlines`, `rightToLeft`, `rowCount`, `columnCount`, `filter`, `conditional[i]`, `protected` |
| range | `format`, `borders`, `merge`, `note`, `validation`, `protected` |
| row | `height`, `hidden`, `autofit` |
| column | `width`, `hidden`, `autofit` |

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

## drive-cli — Drive-native CLI (same binary, multi-call)

Drive operations addressed by **file/folder ID** (not the `SID:Sheet!locator`
grammar) run under the name `drive-cli`, so sheet-cli's grammar stays clean.
It's the **same binary** as sheet-cli: `sheet_cli/multicall.py` dispatches on
`basename(argv[0])` (a name starting with `drive` → Drive CLI, else Sheets
CLI), and both console scripts point at it. It shares the `sheet_client`
library and the OAuth token. The destination folder is an optional positional
argument.

```
drive-cli list    [FOLDER]                  list files (root, or inside FOLDER)
drive-cli copy    ID [FOLDER] [--name NAME] copy file/folder (folders recurse)
drive-cli new     folder NAME [FOLDER]      create a folder
drive-cli new     sheet  NAME [FOLDER]      create a spreadsheet
drive-cli move    ID FOLDER [--add]         move into FOLDER (--add = multi-parent)
drive-cli parents ID                        list folders containing ID
drive-cli upload  FILE [ID] [--raw|--to K]  upload a local file (ID = folder, or file to replace)
drive-cli export  ID FILE [--mime TYPE]     write a Drive file out locally
```

`copy` auto-detects by mimeType: folder → recursive, spreadsheet → `files.copy`,
other → generic `files.copy`. `drive_cli/ops.py` is the shared verb core, reused
by the MCP server's `drive_*` tools. Use `sheet-cli` for cells/sheets/structure,
`drive-cli` for files/folders.

`SheetsClient.copy_folder` is the one composed helper in the library, an
exception to "no helpers": Drive has no recursive-copy call, so the recursion
has to live somewhere, and it stays inside that one method.

`upload` resolves its optional `ID` the same way: a folder creates inside it,
anything else replaces that file's bytes via `files.update`, keeping the ID, URL,
sharing and comments. It converts to the matching Google type by default —
`--raw` stores the bytes as-is, `--to doc|sheet|slides` forces a type. `export`
branches on the source: a `google-apps.*` file is a `files.export`, anything else
a plain media download, so `--mime` on one is an error. `drive_cli/mimes.py`
holds the extension and export tables and imports nothing, so it tests offline.

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

**Bulk writes with `--file`:**

Pass a JSON payload from a file instead of stdin — no heredoc, no generator
script. Write the file with the Write tool, then:

```bash
sheet-cli put SPREADSHEET_ID:Sheet1 --file cells.json
```

Keys are A1 addresses relative to the target sheet (no `Sheet1!` prefix —
it's inherited from the target):

```json
{"A1": "Name", "B1": 42, "C1": "=A1&B1"}
```

`--file -` reads stdin explicitly, so the same flag works whether the payload
is on disk or piped. `put`, `new`, and `batch` all accept it.

**Building a sheet with `batch`:**

One file, one command, values + formatting + structure:

```bash
sheet-cli batch SPREADSHEET_ID --file ops.json
```

`ops.json` is a list of operations. Each names a sheet and a range (or a row /
column) and carries one or more actions:

```json
[
  {"range": "Sheet1!A1:D35", "values": [["Total", "", "=B10", ""]]},
  {"range": "Sheet1!B6:B10", "format": {"numberFormat": {"type": "CURRENCY", "pattern": "\"$\"#,##0"}}},
  {"column": "Sheet1!A", "width": 220}
]
```

Actions: `values`, `clear`, `format`, `borders`, `note`, `merge`, `validation`,
`width`, `height`. An op may carry several at once. Value writes go to
`values.batchUpdate`, clears to `values.batchClear`, and the rest to
`spreadsheets.batchUpdate` — three calls at most, not atomic across them.

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
