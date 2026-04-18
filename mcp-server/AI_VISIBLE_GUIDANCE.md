# AI-Visible Guidance in MCP Server

Agents connecting to `sheet-service.py` over stdio see tool descriptions but never
this file — it mirrors what `tools/list` returns, for human review.

The v2 server exposes **seven tools** that map to the `sheet-cli` verb grammar,
plus `sheets_batch_update` as an escape hatch for advanced Sheets API features.

---

## Tool: sheets_get

Read from a target. Returns raw Google API responses.

```
TARGET SHAPES:
- '' (empty)              → Drive listing (list of spreadsheets the user can see)
- 'SID'                   → whole spreadsheet metadata (meta_read)
- 'SID:Sheet1'            → all values in Sheet1
- 'SID:Sheet1!A1:B10'     → values in range
- 'SID:Sheet1!5'          → row 5
- 'SID:Sheet1!C'          → column C

FORMAT:
- 'json' (default): raw Google API response as-is
- 'text': cell/value pairs — 'A1 hello\nB1 42' — useful for small reads to save tokens

BEST PRACTICES:
- For complex analysis of many cells, request 'json' and parse the structure directly
- For quick inspection (< 50 cells), 'text' is more compact
```

---

## Tool: sheets_put

Write cells to a target. Batches into one API call.

```
DATA SHAPES:
- {"A1": "hello", "B1": 42}              — cell-keyed dict, each becomes a 1x1 write
- {"A1:B2": [[1,2],[3,4]]}               — range-keyed dict, values are 2D
- [[1,2],[3,4]]                          — bare 2D array; target must be a range
- scalar ("hello" / 42)                  — single-cell write; target must be a cell

Keys without '!' are qualified with the target's sheet. Keys with '!' pass through.

FORMULAS: prefix with '=' ('=SUM(A1:A10)'). Google parses in USER_ENTERED mode.

BULK WRITES (10+ cells): generate the full dict programmatically and send in ONE call.
A single sheets_put scales to thousands of cells — do NOT loop over sheets_put.
```

---

## Tool: sheets_del

Delete or clear what's at the target.

```
BEHAVIOR BY TARGET TYPE:
- SPREADSHEET   → Drive delete (moves to trash)
- SHEET         → deleteSheet
- RANGE         → clear values (preserves formatting and notes)
- ROW/COLUMN    → deleteDimension

There is no Drive-level del — bare empty target is rejected.
```

---

## Tool: sheets_new

Create a new spreadsheet, sheet, row, or column.

```
BEHAVIOR BY TARGET:
- '' or 'Title'        → new spreadsheet (target is treated as the title)
- 'SID:NewSheetName'   → add a sheet
- 'SID:Sheet1!5'       → insert a row (side: 'above'|'below', default 'below')
- 'SID:Sheet1!C'       → insert a column (side: 'left'|'right', default 'right')

Returns the new resource. For a new spreadsheet the response includes
spreadsheetId and spreadsheetUrl — store these for subsequent operations.
```

---

## Tool: sheets_copy

Copy source to dest. Uses server-side APIs when possible.

```
DISPATCH TABLE:
- same spreadsheet, RANGE→RANGE   → copyPaste    (server-side, no data transfer)
- cross spreadsheet, whole SHEET  → sheets.copyTo (server-side, no data transfer)
- other shapes                    → read + write fallback

INHERITANCE: dest can omit components to inherit from source:
- 'Sheet2!D1'    → same SID as source, different sheet
- '!D1'          → same SID and same sheet as source
- ':Sheet2'      → same SID, different sheet
```

---

## Tool: sheets_move

Move source to dest. Uses server-side APIs when possible.

```
DISPATCH TABLE:
- same sheet, ROW/COL              → moveDimension (server-side)
- same spreadsheet, RANGE→RANGE    → cutPaste      (server-side)
- cross-spreadsheet                → copy + delete (never server-side)

Same inheritance rules as sheets_copy.
```

---

## Tool: sheets_batch_update

Raw `spreadsheets.batchUpdate` escape hatch. Use for things that don't fit the
verb grammar:

```
- formatting: repeatCell, updateCells
- structure: merges, protected ranges, named ranges
- UX: conditional rules, auto-resize, find/replace, sortRange, setBasicFilter

CALL sheets_get 'SID' FIRST to discover sheetId values for GridRange.
BATCH multiple requests in one call.

Reference: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request
```

---

## Why This Matters

Agents connecting over stdio see only what the JSON-RPC protocol returns.
Embedding guidance in tool descriptions means every agent receives the same
best practices on first connect — no separate docs lookup required.

Keep these descriptions **terse and operational**: the target grammar, dispatch
table, inheritance rules, and bulk-write pattern. Long prose goes in the project
docs (README, llms.txt), not the tool description.

---

## Verification

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | ./mcp-server/sheet-service.sh
```

Should return seven tools: `sheets_get`, `sheets_put`, `sheets_del`,
`sheets_new`, `sheets_copy`, `sheets_move`, `sheets_batch_update`.

---

**MCP Server Version:** 2.0.0
**Protocol:** JSON-RPC 2.0 over stdio
