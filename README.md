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
SID.locale                 IETF locale (e.g. "en_US")
SID.timeZone               IANA time zone
SID.autoRecalc             ON_CHANGE | MINUTE | HOUR
SID.theme                  SpreadsheetTheme (primary font + themeColors)
SID.defaultFormat          default CellFormat applied to empty cells
SID.iterativeCalc          IterativeCalculationSettings
SID.named.sales            a named range (keyed by name)
SID.parents                Drive folder IDs containing the spreadsheet
SID.parents.FOLDER_ID      membership of a specific folder
SID:Sheet.title            sheet tab title
SID:Sheet.index            tab position
SID:Sheet.freeze           frozen rows / columns
SID:Sheet.color            tab color
SID:Sheet.hidden           tab visibility
SID:Sheet.hideGridlines    whether gridlines are hidden
SID:Sheet.rightToLeft      RTL layout
SID:Sheet.rowCount         grid row count
SID:Sheet.columnCount      grid column count
SID:Sheet.filter           basic filter (singleton per sheet)
SID:Sheet.conditional[0]   conditional-format rule by index
SID:Sheet.protected        whole-sheet protection (supports unprotectedRanges)
SID:Sheet!A1:B2.format     cell format for a range
SID:Sheet!A1:B2.borders    borders
SID:Sheet!A1:B2.merge      merges
SID:Sheet!A1:B2.note       notes
SID:Sheet!A1:B2.validation data validation
SID:Sheet!A1:B2.protected  protected range
SID:Sheet!5.height         row pixel height
SID:Sheet!5.hidden         row visibility
SID:Sheet!5.autofit        auto-resize row (put only)
SID:Sheet!C.width          column pixel width
SID:Sheet!C.hidden         column visibility
SID:Sheet!C.autofit        auto-resize column (put only)
```

`copy` and `move` do not accept `.property` targets. Scalar sugar works
for simple properties (`put .freeze "2 1"`, `put .color "#ff00aa"`,
`put .title "New"`, `put .parents FOLDER_ID`); structured request bodies
come from stdin as JSON. `.parents` is the only property that routes
through the Drive API (everything else is pure Sheets API).

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

# Duplicate a whole spreadsheet (server-side via Drive files.copy)
sheet-cli copy SID "Q3 Backup"
sheet-cli copy SID ""           # default "Copy of ..." title

# Move a row
sheet-cli move SID:Sheet1!5 !2

# Drive folder membership
sheet-cli get SID.parents                 # list folder IDs
sheet-cli put SID.parents FOLDER_ID       # move to a folder (replace)
sheet-cli new SID.parents FOLDER_ID       # add a folder (no remove)
sheet-cli del SID.parents.FOLDER_ID       # remove a specific folder

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

## drive-cli — Drive files & folders

`drive-cli` is the **same binary** invoked under a different name (a multi-call
launcher dispatches on `argv[0]`). It handles Drive-native operations addressed
by plain **file/folder ID** (not the `SID:Sheet!locator` grammar), sharing the
same library and cached OAuth token. The destination folder is an optional
positional argument; mutations print JSON, `list`/`parents` are text-first.

```
drive-cli list    [FOLDER]                  list files (root, or inside FOLDER)
drive-cli copy    ID [FOLDER] [--name NAME] copy file/folder, optionally into FOLDER
drive-cli new     folder NAME [FOLDER]      create a folder, optionally inside FOLDER
drive-cli new     sheet  NAME [FOLDER]      create a spreadsheet, optionally inside FOLDER
drive-cli move    ID FOLDER [--add]         move into FOLDER (--add keeps existing parents)
drive-cli parents ID                        list the folders containing ID
drive-cli upload FILE [ID] [--raw|--to doc|sheet|slides]  put a local file into Drive
drive-cli export ID FILE [--mime TYPE]      write a Drive file out as a local file
drive-cli inventory ROOT [-o MANIFEST]      walk a tree, recording each node's owner
drive-cli plan   ROOT --to EMAIL           report which owners must act, without changing anything
drive-cli chown  MANIFEST --to EMAIL        transfer one owner's files to a new owner
drive-cli accept MANIFEST                   accept every pending transfer, as the new owner
drive-cli auth                              run OAuth flow
```

Every command takes `--as EMAIL`, which selects the cached token at
`~/.sheet-cli/token-EMAIL.json` instead of the shared default. A transfer runs
as each source owner in turn and then as the new owner, so each needs its own
token: run `drive-cli auth --as EMAIL` once per account.

```bash
# Copy any file type; a folder is copied recursively
drive-cli copy FILE_ID DEST_FOLDER --name "Renamed copy"
drive-cli copy FOLDER_ID DEST_FOLDER

# Create
drive-cli new folder "Q3 docs" PARENT_FOLDER
drive-cli new sheet  "Budget" PARENT_FOLDER

# Relocate / inspect
drive-cli move FILE_ID DEST_FOLDER
drive-cli parents FILE_ID
drive-cli list PARENT_FOLDER
```

Upload and export:

```bash
drive-cli upload flyer.docx              # -> a Google Doc in My Drive root
drive-cli upload flyer.docx FOLDER_ID    # -> a Google Doc in that folder
drive-cli upload flyer.docx DOC_ID       # -> replaces that Doc, same URL
drive-cli upload flyer.docx --raw        # -> stored as .docx, no conversion
drive-cli upload notes.txt --to doc      # -> force a Doc
drive-cli upload data --mime text/csv    # -> no extension, so state the type

drive-cli export DOC_ID   out.pdf        # Doc   -> PDF
drive-cli export DOC_ID   out.docx       # Doc   -> Word
drive-cli export SHEET_ID out.csv        # Sheet -> CSV
drive-cli export PDF_ID   out.pdf        # not native: a plain download
```

`upload` converts to the matching Google type by default: `.docx .doc .odt .rtf
.txt .html .md` become a Doc, `.xlsx .xls .csv .tsv .ods` a Sheet, `.pptx .ppt
.odp` Slides. Anything else uploads as-is. Passing a file ID rather than a
folder ID replaces that file's bytes, keeping its ID, URL, sharing and comments.

Export extensions are what Drive offers per type: Doc `pdf docx odt rtf txt html
epub`, Sheet `pdf xlsx ods csv tsv zip`, Slides `pdf pptx odp txt`. Drive
refuses to export a document over 10MB.

`copy` auto-detects the source type by mimeType: folder → recursive copy,
spreadsheet → `files.copy`, any other file → generic `files.copy`. The same
operations are exposed to Claude via the MCP `drive_*` tools.

### Transferring ownership of a tree

Ownership transfer changes a permission on the existing file, so file IDs,
URLs, embeds, and `IMPORTRANGE` references all survive. Copying does not — it
mints new IDs.

Ownership does not cascade, and the flags that move it live on a direct
per-file permission that cannot be inherited from a parent folder. A tree of
3,000 items is 3,000 calls. The three commands split that by who has to be
authenticated for each call:

```bash
# 1. Survey — any account that can see the whole tree (usually the new owner,
#    who has inherited Editor access from the top folder). `plan` walks the tree
#    and reports the work without touching anything; `-o` saves the manifest.
drive-cli plan ROOT_FOLDER_ID --to=bob@example.com -o transfer.json --as=bob@example.com

# 2. Transfer — once per source owner, authenticated as that owner.
drive-cli chown transfer.json --to bob@example.com --as alice@example.com
drive-cli chown transfer.json --to bob@example.com --as carl@example.com

# 3. Accept — once, as the new owner. Covers every source owner's files.
drive-cli accept transfer.json --as bob@example.com

# 4. Reparent the top of the tree into the new owner's My Drive.
drive-cli move ROOT_FOLDER_ID DEST_FOLDER_ID --as bob@example.com
```

`chown` picks its path per file. Two Google Workspace accounts in the same
organization transfer in one call. Consumer accounts get `pendingOwner=true`
and an email, and ownership does not move until `accept` runs. `--mode direct`
or `--mode pending` forces one path; the default `auto` tries direct and falls
back when Drive answers `consentRequiredForOwnershipTransfer`,
`cannotTransferOwnershipToNonWorkspaceUser`, or
`ONLY_PENDING_OWNER_CAN_BECOME_NEW_OWNER` (a node this run already offered).

`plan` is the dry run for the whole operation. It reads the tree (or an existing
manifest, with `-m`) and reports every account that owns something, how many
folders and files each still holds, which of them have a cached token and which
need `drive-cli auth` first, what cannot be transferred at all, and the exact
commands to run in order. It makes no changes:

```
root      1MIZ6ZsmmILgvWr2ZamYj_C4bA-2NrBGj
surveyed  bob@example.com
target    bob@example.com
nodes     412 (409 to transfer, 3 already owned)

owners who must run chown (each authenticates as itself):
  alice@example.com      380 items (24 folders, 356 files)  token cached
  carl@example.com        29 items (2 folders, 27 files)    NEEDS LOGIN

cannot transfer (shared drive): 2
  1AbC…  quarterly-figures
  1DeF…  vendor-list

up to 1636 Drive calls

run first:
  drive-cli auth --as=carl@example.com
```

Re-run `plan -m transfer.json --to=EMAIL` between passes to see what is left.

`chown` takes `--limit N` to stop after N nodes and `--only ID` (repeatable) to
transfer a single node, so a large slice can be smoke-tested before it is
released in full.

### Progress and checkpoints

`chown` and `accept` print one line per node to stderr, leaving stdout as pure
JSON, so a run can be piped and watched at the same time:

```
[   37/653] pending        file   Pro-Forma Comments 10_18       0h01m15s elapsed, 0h20m56s left
```

`--log PATH` appends the same lines to a file, `--quiet` turns them off. The
manifest is saved every 25 nodes (`--checkpoint N`), so a run killed partway
keeps the record of what it already did and the next run picks up from there.

Remember that `chown` alone changes nothing visible: it only marks each file
`pendingOwner`. Files change hands during `accept`, so that is the pass to watch
if you are checking the Drive UI.

### Rate limits

Drive allows 325,000 quota units per minute per user; a permission write costs
50, so the per-minute quota is not the binding constraint on a transfer. The
practical limit is Drive's own throttling of sharing operations, which comes
back as **403 with reason `rateLimitExceeded` or `userRateLimitExceeded`**, not
only as 429. `_execute_with_retry` treats those, plus `sharingRateLimitExceeded`
and `quotaExceeded`, as retryable — five attempts with exponential backoff and
jitter, capped at 64 seconds. Every other 403 (`insufficientFilePermissions`,
say) still fails immediately, since retrying a refusal is pointless.

`--pace SECONDS` on `chown` and `accept` sleeps between nodes to stay under the
limit rather than backing off after hitting it. On a several-hundred-node slice,
`--pace 0.2` costs a couple of minutes and keeps the run near 5 nodes/second.
Nothing is lost to a throttle in any case: the manifest records each node, so a
run that dies partway resumes where it stopped.

The manifest records the outcome per node, so runs are resumable and `accept`
knows exactly what is outstanding. `--dry-run` reports what would change without
calling Drive, and `--verbose` adds the per-node results to the summary.

Limits worth knowing before a large run:

- Files on shared drives cannot be transferred — the organization owns them.
  `inventory` flags those nodes and `chown` skips them.
- Cross-organization Workspace transfers are refused by Drive.
- Service accounts cannot receive ownership; they have no storage quota.
- `files.list` only returns what the surveying account can see, so anything not
  shared with it is missing from the manifest. Compare `owners` counts against
  what you expect before starting.
- Transferred files count against the new owner's storage quota.
- Shortcuts cannot be transferred at all. Drive answers `400 ... The action
  cannot be performed on an item of mime-type
  application/vnd.google-apps.shortcut`, so `chown` skips them and `plan` counts
  them as untransferable rather than as work. They stay with their current
  owner, still pointing at the same target. To move one, delete it and create a
  new shortcut as the new owner, which changes the shortcut's ID.
- After `accept`, the tree root has no parent the new owner can see, so it lands
  in their "Shared with me" until step 4 reparents it. Everything nested below
  it follows the root and needs no move of its own.
- The old owner keeps writer access on every transferred file. Removing that is
  a separate sharing change.

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
- `copy_spreadsheet(source_id, new_title=None, parent_folder_id=None)` - Duplicate a whole spreadsheet via Drive `files.copy`
- `copy_file(source_id, new_title=None, parent_folder_id=None)` - Copy any Drive file via `files.copy` (generic)
- `copy_folder(source_id, new_title=None, parent_folder_id=None)` - Recursively copy a Drive folder and its contents
- `create_folder(name, parent_folder_id=None)` - Create an empty Drive folder
- `get_file_mime(file_id)` - Drive mimeType of a file/folder
- `list_files(folder_id=None, include_shared_drives=False)` - List Drive files of any type
- `delete_spreadsheet(spreadsheet_id)` - Delete a spreadsheet via Drive API
- `get_parents(spreadsheet_id)` - List Drive folder parents of a spreadsheet
- `update_parents(spreadsheet_id, add=None, remove=None)` - Add/remove Drive folder parents
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
│   ├── sheet_cli/            # CLI layer
│   │   ├── multicall.py      # Multi-call launcher (dispatch on argv[0])
│   │   ├── cli.py            # Six-verb argparse entry point
│   │   ├── grammar.py        # Target-string grammar (parse/resolve/classify)
│   │   ├── properties.py     # Property handler registry (.format, .freeze, …)
│   │   ├── verbs.py          # get / put / del / new dispatch
│   │   ├── dispatch.py       # copy / move with server-side optimizations
│   │   ├── formats.py        # stdin/stdout formatters
│   │   └── __main__.py       # `python -m sheet_cli`
│   └── drive_cli/            # Drive-native CLI (file/folder IDs)
│       ├── cli.py            # list/copy/new/move/parents argparse entry point
│       └── ops.py            # Shared verb core (also used by the MCP server)
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
