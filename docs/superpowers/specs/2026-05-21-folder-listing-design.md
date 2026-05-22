# Folder-Scoped Drive Listing

**Date:** 2026-05-21
**Status:** Approved

## Problem

`sheets_get ""` (MCP) and `sheet-cli get` (CLI) list every spreadsheet the authenticated user can see. There is no way to scope the listing to a specific Drive folder. Agents that need to operate on all sheets in a folder must write ad-hoc Python to call the Drive API directly.

## Solution

Add an optional `folder_id` parameter at three layers — `SheetsClient`, MCP tool, CLI flag — so agents can request folder-scoped listings without leaving the existing tool surface.

## Layer 1 — `SheetsClient.list_spreadsheets()`

**File:** `src/sheet_client/client.py`

Add `folder_id: Optional[str] = None` to the signature. When set, prepend `'<folder_id>' in parents and` to the existing Drive query string. All other behavior (pagination, `include_shared_drives`, field selection) unchanged.

```python
def list_spreadsheets(
    self,
    folder_id: Optional[str] = None,
    include_shared_drives: bool = False,
) -> List[dict]:
```

## Layer 2 — MCP `sheets_get` tool

**File:** `mcp-server/sheet-service.py`

Add `folder_id` (optional string) to `sheets_get` `inputSchema`. Pass it through to `list_spreadsheets()` when the target is DRIVE. Return a grammar error if `folder_id` is provided with a non-empty target.

Schema addition:
```json
"folder_id": {
    "type": "string",
    "description": "Drive folder ID. Only valid when target is empty (Drive listing). Filters results to spreadsheets directly inside this folder."
}
```

Tool description update — add to the `TARGET SHAPES` block:
```
- '' + folder_id   → spreadsheets directly inside a specific Drive folder
```

## Layer 3 — CLI `get` command

**File:** `src/sheet_cli/cli.py` and `src/sheet_cli/verbs.py`

Add `--folder FOLDER_ID` to the `get` subparser. Validate: if `--folder` is given and the target is not DRIVE, exit with an error message. Pass `folder_id` as a keyword argument to `do_get`, which forwards it to `list_spreadsheets()`.

```
sheet-cli get --folder 1vpPLfFRz3a_EX--8-V1bZ2ywwXqFY1_o
```

`do_get` signature change:
```python
def do_get(client: SheetsClient, target: Target, folder_id: Optional[str] = None) -> Any:
```

## Error Cases

| Condition | Behavior |
|---|---|
| `folder_id` given with non-empty MCP target | Grammar error: "folder_id only applies to Drive-level listing" |
| `--folder` given with non-DRIVE CLI target | CLI error exit with same message |
| `folder_id` is a valid ID but empty folder | Returns empty list (not an error) |
| `folder_id` is an invalid/inaccessible ID | Drive API returns 404 or 403 — propagated as `SheetsAPIError` |

## Out of Scope

- Recursive folder traversal (subfolders)
- Listing non-spreadsheet files
- Any other Drive operations (rename folder, create folder, etc.)
