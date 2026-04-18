#!/usr/bin/env python3
"""MCP Server for Google Sheets — v2 unified grammar.

Exposes the same six-verb grammar as the `sheet-cli` command-line tool,
plus a raw `sheets_batch_update` escape hatch for advanced formatting and
structure operations that don't fit in the verb model.

Target-string grammar (SID = spreadsheet ID):

    <empty>                      Drive-level listing
    SID                          a spreadsheet
    SID:Sheet                    a sheet by title
    SID:Sheet!A1                 a cell
    SID:Sheet!A1:B10             a range
    SID:Sheet!5                  row 5
    SID:Sheet!C                  column C
    SID:!A1                      range in the first/default sheet

Any target may carry a .property suffix to address formatting, structure, or
metadata of the resource (always returned as JSON):

    SID.title                    spreadsheet title
    SID.named.NAME               named range
    SID:Sheet.freeze             frozen rows/cols
    SID:Sheet.color              tab color
    SID:Sheet.conditional[i]     conditional-format rule by index
    SID:Sheet!A1:B2.format       cell format on a range
    SID:Sheet!5.height           row pixel height
    SID:Sheet!C.width            column pixel width

Second-operand short forms for copy/move inherit from the first:
    Sheet!A1     inherits SID
    !A1          inherits SID + sheet
    :Sheet       inherits SID

copy/move do NOT accept .property targets.

Sheet names containing ':', '!', '.', spaces, or "'" must be single-quoted:
    SID:'My Sheet'!A1
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import dispatch, verbs
from sheet_cli.grammar import (
    GrammarError,
    Target,
    TargetType,
    classify,
    parse,
    resolve,
)
from sheet_client import SheetsClient


def _parse_first(s: str) -> Target:
    """Parse a first-operand target. Empty string is DRIVE."""
    parsed = parse(s or "")
    if parsed.is_empty:
        return Target(None, None, None)
    if parsed.spreadsheet_id is None:
        raise GrammarError(f"target must include a spreadsheet ID: {s!r}")
    return Target(parsed.spreadsheet_id, parsed.sheet, parsed.locator, parsed.property)


def _parse_second(s: str, parent: Target) -> Target:
    return resolve(parent, parse(s or ""))


class MCPSheetsServer:
    """MCP server exposing the unified six-verb grammar over Google Sheets."""

    def __init__(self):
        self.client: Optional[SheetsClient] = None

    def initialize(self):
        if self.client is None:
            self.client = SheetsClient()

    # ------------------------------------------------------------------
    # tool catalog
    # ------------------------------------------------------------------

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "sheets_get",
                "description": """Read from a target. Returns raw Google API responses.

TARGET SHAPES:
- '' (empty)              → Drive listing (list of spreadsheets the user can see)
- 'SID'                   → whole spreadsheet metadata (meta_read)
- 'SID:Sheet1'            → all values in Sheet1
- 'SID:Sheet1!A1:B10'     → values in range
- 'SID:Sheet1!5'          → row 5
- 'SID:Sheet1!C'          → column C

PROPERTIES (.property suffix on any target — always returns JSON):
- spreadsheet:  .title, .named (list), .named.NAME (one)
- sheet:        .title, .freeze, .color, .hidden, .conditional (list), .conditional[i] (one)
- range:        .format, .borders, .merge, .note, .validation, .protected
- row:          .height
- column:       .width
Examples: 'SID.title', 'SID:Sheet1.freeze', 'SID:Sheet1!A1:B2.format', 'SID.named.sales'.

FORMAT:
- 'json' (default): raw Google API response as-is
- 'text': cell/value pairs — 'A1 hello\\nB1 42' — useful for small reads to save tokens
  Property targets, DRIVE, and SPREADSHEET always return JSON regardless.

BEST PRACTICES:
- For complex analysis of many cells, request 'json' and parse the structure directly
- For quick inspection (< 50 cells), 'text' is more compact""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target string. Empty for Drive listing.",
                            "default": "",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["json", "text"],
                            "default": "json",
                            "description": "Output format. DRIVE/SPREADSHEET always return JSON.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "sheets_put",
                "description": """Write cells (or properties) to a target. Batches into one API call.

DATA SHAPES (cell writes):
- {"A1": "hello", "B1": 42}              — cell-keyed dict, each becomes a 1x1 write
- {"A1:B2": [[1,2],[3,4]]}                — range-keyed dict, values are 2D
- [[1,2],[3,4]]                           — bare 2D array; target must be a range
- scalar ("hello" / 42)                   — single-cell write; target must be a cell

Keys without '!' are qualified with the target's sheet. Keys with '!' pass through.

FORMULAS: prefix with '=' ('=SUM(A1:A10)'). Google parses in USER_ENTERED mode.

PROPERTY WRITES (target carries .property suffix):
- '.title'                  → string ('Q3 Report')
- '.color' / tab color      → '#rrggbb' or {"red":r,"green":g,"blue":b} (channels in [0,1])
- '.freeze'                 → "rows" / "rows cols" / {"rows":N,"columns":M}
- '.hidden'                 → bool
- '.note'                   → string (applied to whole range)
- '.format' / '.borders' / '.validation'
                            → JSON object matching the Sheets API request shape
- '.conditional' (append)   → ConditionalFormatRule
- '.conditional[i]' (replace at index)
                            → ConditionalFormatRule
- '.named.NAME'             → 'Sheet1!A1:B100' (A1) or a GridRange dict
- '.height' / '.width'      → integer pixel size
Property responses are always JSON. Use sheets_get '.property' first to inspect current state.

BULK WRITES (10+ cells): generate the full dict programmatically and send in ONE call.
A single sheets_put scales to thousands of cells — do NOT loop over sheets_put.""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target string (cell, range, or sheet).",
                        },
                        "data": {
                            "description": "Cell-keyed dict, range-keyed dict, 2D array, or scalar.",
                        },
                    },
                    "required": ["target", "data"],
                },
            },
            {
                "name": "sheets_del",
                "description": """Delete or clear what's at the target.

BEHAVIOR BY TARGET TYPE:
- SPREADSHEET   → Drive delete (moves to trash)
- SHEET         → deleteSheet
- RANGE         → clear values (preserves formatting and notes)
- ROW/COLUMN    → deleteDimension

There is no Drive-level del — bare empty target is rejected.

PROPERTY DELETES (.property suffix): reset / clear the property in place
- '.format' / '.borders' / '.note' / '.validation' / '.merge' → clear it on the range
- '.freeze' → set frozen rows/cols to 0
- '.color' / '.hidden' → reset to defaults
- '.protected' → delete every protected range overlapping the target
- '.named.NAME' → remove that named range
- '.conditional' (no key) → delete every rule on the sheet
- '.conditional[i]' → delete that rule""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target string.",
                        },
                    },
                    "required": ["target"],
                },
            },
            {
                "name": "sheets_new",
                "description": """Create a new spreadsheet, sheet, row, column, or collection element.

BEHAVIOR BY TARGET:
- '' or 'Title'        → new spreadsheet (target is treated as the title)
- 'SID:NewSheetName'   → add a sheet
- 'SID:Sheet1!5'       → insert a row (side: 'above'|'below', default 'below')
- 'SID:Sheet1!C'       → insert a column (side: 'left'|'right', default 'right')

Returns the new resource. For a new spreadsheet the response includes
spreadsheetId and spreadsheetUrl — store these for subsequent operations.

PROPERTY APPENDS (collections only — pass `data`):
- 'SID:Sheet1.conditional'  → data = ConditionalFormatRule (appended at end)
- 'SID.named.NAME'          → data = 'Sheet1!A1:B100' or GridRange dict
- 'SID:Sheet1!A1:B2.merge'  → data = 'MERGE_ALL' | 'MERGE_COLUMNS' | 'MERGE_ROWS' (default MERGE_ALL)
- 'SID:Sheet1!A1:B2.protected' → data = ProtectedRange spec dict (range filled in for you)

Use sheets_put for non-collection property writes.""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "default": "",
                            "description": "Target or title.",
                        },
                        "side": {
                            "type": "string",
                            "enum": ["above", "below", "left", "right"],
                            "description": "For row/column targets only.",
                        },
                        "data": {
                            "description": "Body for property appends (.conditional rule, .named A1/GridRange, .merge type, .protected spec). Ignored for non-property targets.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "sheets_copy",
                "description": """Copy source to dest. Uses server-side APIs when possible.

DISPATCH TABLE:
- same spreadsheet, RANGE→RANGE   → copyPaste   (server-side, no data transfer)
- cross spreadsheet, whole SHEET  → sheets.copyTo (server-side, no data transfer)
- other shapes                     → read + write fallback

INHERITANCE: dest can omit components to inherit from source:
- 'Sheet2!D1'    → same SID as source, different sheet
- '!D1'          → same SID and same sheet as source
- ':Sheet2'      → same SID, different sheet

NOT SUPPORTED for .property targets — use sheets_get + sheets_put to copy a property value.""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source target."},
                        "dest": {"type": "string", "description": "Destination target (may inherit from source)."},
                    },
                    "required": ["source", "dest"],
                },
            },
            {
                "name": "sheets_move",
                "description": """Move source to dest. Uses server-side APIs when possible.

DISPATCH TABLE:
- same sheet, ROW/COL              → moveDimension (server-side)
- same spreadsheet, RANGE→RANGE    → cutPaste (server-side)
- cross-spreadsheet                → copy + delete (never server-side)

Same inheritance rules as sheets_copy.
NOT SUPPORTED for .property targets.""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source target."},
                        "dest": {"type": "string", "description": "Destination target (may inherit from source)."},
                    },
                    "required": ["source", "dest"],
                },
            },
            {
                "name": "sheets_batch_update",
                "description": """Raw spreadsheets.batchUpdate escape hatch for operations that don't fit the verb grammar:
formatting (repeatCell, updateCells), conditional rules, merges, protected ranges,
named ranges, auto-resize, find/replace, sortRange, etc.

CALL sheets_get 'SID' FIRST to discover sheetId values needed in GridRange objects.

BATCH MULTIPLE REQUESTS in one call — one formatting operation per call is wasteful.

Reference: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Array of Request objects (addSheet, repeatCell, etc.).",
                        },
                    },
                    "required": ["spreadsheet_id", "requests"],
                },
            },
        ]

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        self.initialize()
        assert self.client is not None

        if name == "sheets_get":
            target = _parse_first(args.get("target", ""))
            response = verbs.do_get(self.client, target)
            if args.get("format") == "text":
                return _format_as_text(target, response)
            return response

        if name == "sheets_put":
            target = _parse_first(args["target"])
            return verbs.do_put(self.client, target, args["data"])

        if name == "sheets_del":
            target = _parse_first(args["target"])
            return verbs.do_del(self.client, target)

        if name == "sheets_new":
            target = _parse_first(args.get("target", ""))
            return verbs.do_new(
                self.client, target,
                side=args.get("side"),
                data=args.get("data"),
            )

        if name == "sheets_copy":
            source = _parse_first(args["source"])
            dest = _parse_second(args["dest"], source)
            return dispatch.do_copy(self.client, source, dest)

        if name == "sheets_move":
            source = _parse_first(args["source"])
            dest = _parse_second(args["dest"], source)
            return dispatch.do_move(self.client, source, dest)

        if name == "sheets_batch_update":
            return self.client.meta_write(args["spreadsheet_id"], args["requests"])

        raise ValueError(f"unknown tool: {name}")

    # ------------------------------------------------------------------
    # JSON-RPC
    # ------------------------------------------------------------------

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "initialize":
            self.initialize()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "sheets-mcp-server", "version": "2.0.0"},
                    "capabilities": {"tools": {}},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": self.get_tools()},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result = self.execute_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": result if isinstance(result, str)
                             else json.dumps(result, indent=2, default=str)}
                        ]
                    },
                }
            except GrammarError as e:
                return _rpc_error(request_id, -32602, f"grammar error: {e}")
            except Exception as e:
                return _rpc_error(request_id, -32603, str(e))

        return _rpc_error(request_id, -32601, f"method not found: {method}")

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                print(json.dumps(_rpc_error(None, -32700, f"parse error: {e}")), flush=True)
            except Exception as e:
                print(json.dumps(_rpc_error(None, -32603, f"internal error: {e}")), flush=True)


def _rpc_error(request_id, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _format_as_text(target: Target, response: Any) -> str:
    """Flatten a values response into 'A1 val' lines for cell-level targets.

    Properties always return JSON (their responses aren't cell-shaped).
    """
    if target.property is not None:
        return json.dumps(response, indent=2, default=str)
    tt = classify(target)
    if tt in (TargetType.DRIVE, TargetType.SPREADSHEET):
        return json.dumps(response, indent=2, default=str)

    # Collect (range_str, values) pairs
    pairs = []
    if isinstance(response, dict):
        if "valueRanges" in response:
            pairs = [(vr.get("range", ""), vr.get("values", [])) for vr in response["valueRanges"]]
        elif "values" in response or "range" in response:
            pairs = [(response.get("range", ""), response.get("values", []))]

    # Lazy-import to avoid circular issues at module load
    from sheet_cli import formats
    flat = {}
    for range_str, values in pairs:
        flat.update(formats.expand_range_to_cells(range_str, values))
    return formats.format_cell_value_pairs(flat)


def main():
    MCPSheetsServer().run()


if __name__ == "__main__":
    main()
