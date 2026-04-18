# Google Sheets MCP Server

Model Context Protocol (MCP) server exposing the `sheet-cli` v2 unified grammar
over JSON-RPC 2.0 / stdio. Authenticates as the current user via OAuth 2.0.

## Overview

Seven tools mirror the CLI verbs plus a raw batch-update escape hatch:

| Tool | Purpose |
|---|---|
| `sheets_get` | Read drive / spreadsheet / sheet / range / row / column |
| `sheets_put` | Write cells (scalar, 2D array, cell-keyed dict, or range-keyed dict) |
| `sheets_del` | Clear range / delete sheet / row / column / spreadsheet |
| `sheets_new` | Create spreadsheet / sheet / insert row / column |
| `sheets_copy` | Copy (server-side `copyPaste` / `copyTo` when possible) |
| `sheets_move` | Move (server-side `cutPaste` / `moveDimension` when possible) |
| `sheets_batch_update` | Raw `batchUpdate` for formatting / conditional rules / merges / etc. |

All tools accept target strings in the unified grammar (`SID:Sheet!A1:B10`),
including the `.property` suffix for formatting, freeze, named ranges,
conditional rules, etc. See [../llms.txt](../llms.txt) for the full grammar
and usage patterns.

**Guidance is embedded in tool descriptions** (see
[AI_VISIBLE_GUIDANCE.md](AI_VISIBLE_GUIDANCE.md)) so agents receive it through
`tools/list` without reading external docs.

## Installation

### Prerequisites

1. Python 3.8+
2. Google Cloud project with the **Sheets API** and **Drive API** enabled
3. OAuth 2.0 Desktop-app credentials saved to `~/.sheet-cli/credentials.json`

### Setup

```bash
cd /home/john/src/sheet-cli
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

First run opens a browser for OAuth consent:

```bash
./mcp-server/sheet-service.sh
```

After auth, `~/.sheet-cli/token.json` is cached (mode 600). Ctrl+C to exit.

## Claude Desktop config

```json
{
  "mcpServers": {
    "sheets": {
      "command": "/home/john/src/sheet-cli/mcp-server/sheet-service.sh"
    }
  }
}
```

The shell script handles venv activation and working directory.

## Tool reference

### sheets_get

Read from a target.

| Parameter | Type | Notes |
|---|---|---|
| `target` | string | `""` for Drive listing; `SID` / `SID:Sheet` / `SID:Sheet!A1:B10` etc. Default `""`. |
| `format` | string | `"json"` (default) or `"text"`. Text mode flattens to `A1 value` pairs. |

### sheets_put

Write cells.

| Parameter | Type | Notes |
|---|---|---|
| `target` | string | Cell / range / sheet. |
| `data` | any | Scalar, 2D array, cell-keyed dict, or range-keyed dict. |

Cell-keyed keys without `!` inherit the target's sheet. Formulas prefixed with `=`.
Batch 10+ cells in a single call — one HTTP round-trip.

### sheets_del

Delete or clear based on target shape (see table above).

### sheets_new

Create spreadsheet / sheet / row / column. `side` applies only to row/column
(`above`/`below` / `left`/`right`). For property collections (`.conditional`,
`.named.NAME`, `.merge`, `.protected`), pass the body via `data`.

### sheets_copy / sheets_move

Binary verbs. `dest` can omit components to inherit from `source`:

- `Sheet2!D1` → same SID
- `!D1` → same SID + same sheet
- `:Sheet2` → same SID, different sheet

Dispatch chooses `copyPaste`, `cutPaste`, `moveDimension`, or `sheets.copyTo`
where possible; falls back to read+write for cross-spreadsheet ranges.

### sheets_batch_update

Escape hatch for the full `spreadsheets.batchUpdate` surface.

```json
{
  "spreadsheet_id": "1abc...",
  "requests": [
    {
      "repeatCell": {
        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
        "cell": {
          "userEnteredFormat": {
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "textFormat": {"bold": true}
          }
        },
        "fields": "userEnteredFormat"
      }
    }
  ]
}
```

Always call `sheets_get "SID"` first to obtain `sheetId` values for `GridRange`.

## Example prompts

```
Read A1:C10 from Sheet1 of 1abc...
List all spreadsheets in Drive
Create a new spreadsheet titled "Q2 Budget"
Add a sheet called "Raw Data" to spreadsheet 1abc...
Insert a row above row 5 in Sheet1
Copy Sheet1 from 1abc... into 1xyz...
Move row 5 in Sheet1 to row 2
Format row 1 of Sheet1 with bold text and a light gray background
```

## Efficiency guidelines

- **< 10 cells**: individual writes are fine.
- **10–100 cells**: batch into one `sheets_put` call.
- **100+ cells**: generate the dict programmatically and send in a single call.
- **Formatting**: batch multiple `requests` in one `sheets_batch_update` call.

## Authentication flow

1. First run: browser OAuth consent.
2. Token cached in `~/.sheet-cli/token.json` (user-only, mode 600).
3. Subsequent runs reuse and auto-refresh the token.
4. Re-auth: delete `token.json` and restart, or run `venv/bin/sheet-cli auth`.

## Troubleshooting

- **"credentials.json not found"** — place it at `~/.sheet-cli/credentials.json`.
- **"Module not found"** — `venv/bin/pip install -r requirements.txt` from project root.
- **"Permission denied" on a sheet** — your account must have access; OAuth scopes include Sheets + Drive.
- **Token expired** — delete `token.json` and re-auth.

## Testing

```bash
venv/bin/python mcp-server/test_server.py
```

Smoke-tests `initialize`, `tools/list`, unknown-method handling, unknown-tool
handling, and grammar-error routing. No Google API calls required.

## Protocol

JSON-RPC 2.0 over stdio. Standard MCP methods: `initialize`, `tools/list`,
`tools/call`. Errors map to standard codes:

| Code | Meaning |
|---|---|
| `-32601` | unknown method |
| `-32602` | grammar error (invalid target string) |
| `-32603` | tool execution error |
| `-32700` | parse error (malformed JSON) |

## See also

- [../llms.txt](../llms.txt) — agent-facing grammar and patterns
- [../README.md](../README.md) — project overview
- [../API.md](../API.md) — `SheetsClient` reference
- [Google Sheets API v4](https://developers.google.com/sheets/api/reference/rest)
- [Model Context Protocol](https://spec.modelcontextprotocol.io)
