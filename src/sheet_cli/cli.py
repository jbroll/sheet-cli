"""Unified sheet-cli — six-verb grammar over Google Sheets & Drive.

Verbs:
    get    TARGET                read a cell / range / sheet / spreadsheet / drive
    put    TARGET [VALUE]        write cells; VALUE is scalar sugar, else stdin
    del    TARGET                clear a range / delete sheet / spreadsheet / row / col
    new    [TARGET] [--side ...] create a spreadsheet / sheet / row / col
    copy   SOURCE DEST           copy (server-side where possible)
    move   SOURCE DEST           move (server-side where possible)

    auth                         OAuth login
    help                         detailed grammar reference

Target grammar:
    SID[:Sheet[!locator]]
    Sheet!locator              (inherit SID from first operand)
    !locator                   (inherit SID and sheet)
    :Sheet                     (inherit SID)

Output rules:
    get        → text (cell/value pairs) by default; --format=json for API shape
    put/del/
    copy/move  → silent; --format=json echoes the target string
    new        → always JSON (the new SID or sheet properties matter)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from sheet_client import SheetsClient
from sheet_client.auth import get_credentials
from sheet_client.exceptions import AuthenticationError, SheetsClientError

from . import dispatch, formats, verbs
from .grammar import (
    GrammarError,
    Target,
    TargetType,
    classify,
    parse,
    render,
    resolve,
)


# ----------------------------- target parsing -----------------------------


def _parse_target(s: str) -> Target:
    """Parse a first-operand target (no inheritance)."""
    parsed = parse(s)
    # First operand must have a SID (unless it's the empty DRIVE target).
    if parsed.is_empty:
        return Target(None, None, None)
    if parsed.spreadsheet_id is None:
        raise GrammarError(f"first operand must include a spreadsheet ID: {s!r}")
    return Target(parsed.spreadsheet_id, parsed.sheet, parsed.locator, parsed.property)


def _parse_second(s: str, parent: Target) -> Target:
    """Parse a second-operand target, inheriting components from parent."""
    return resolve(parent, parse(s))


# ----------------------------- output formatting ----------------------------


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _emit_get(target: Target, response: Any, as_json: bool) -> None:
    tt = classify(target)

    # Properties return arbitrary dicts — always JSON.
    if target.property is not None:
        _print_json(response)
        return

    # DRIVE and SPREADSHEET are always JSON (deeply nested structure).
    if tt in (TargetType.DRIVE, TargetType.SPREADSHEET):
        _print_json(response)
        return

    if as_json:
        _print_json(response)
        return

    # Text: flatten value ranges into cell/value pairs.
    value_ranges = _normalize_value_ranges(response)
    flat = {}
    for range_str, values in value_ranges:
        flat.update(formats.expand_range_to_cells(range_str, values))
    if flat:
        print(formats.format_cell_value_pairs(flat))


def _normalize_value_ranges(response):
    if isinstance(response, dict):
        if "valueRanges" in response:
            return [(vr.get("range", ""), vr.get("values", [])) for vr in response["valueRanges"]]
        if "values" in response or "range" in response:
            return [(response.get("range", ""), response.get("values", []))]
    return []


def _emit_mutation(target: Target, response: Any, as_json: bool) -> None:
    if not as_json:
        return
    _print_json({"target": render(target), "response": response})


# ----------------------------- stdin helpers -------------------------------


def _read_data_from_stdin() -> Optional[Any]:
    text = formats.read_stdin()
    if not text:
        return None
    return formats.parse_input(text)


# --------------------------------- verbs -----------------------------------


def cmd_get(args):
    client = SheetsClient()
    target = _parse_target(args.target or "")
    response = verbs.do_get(client, target)
    _emit_get(target, response, args.format == "json")


def cmd_put(args):
    client = SheetsClient()
    target = _parse_target(args.target)

    if args.value is not None:
        data: Any = args.value
    else:
        data = _read_data_from_stdin()
        # Property targets may accept no body (e.g. ``.autofit``, empty
        # ``.filter``, bare ``.protected``). Let the property layer decide.
        # Value writes still require explicit data.
        if data is None and target.property is None:
            print("put: no value given and no stdin", file=sys.stderr)
            sys.exit(1)

    response = verbs.do_put(client, target, data)
    _emit_mutation(target, response, args.format == "json")


def cmd_del(args):
    client = SheetsClient()
    target = _parse_target(args.target)
    response = verbs.do_del(client, target)
    _emit_mutation(target, response, args.format == "json")


def cmd_new(args):
    client = SheetsClient()
    target = _parse_target(args.target or "")
    # Property collections (e.g. `.conditional`, `.named`) take a body from stdin.
    data = _read_data_from_stdin() if target.property is not None else None
    response = verbs.do_new(client, target, side=args.side, data=data)
    # new always echoes — the user needs the new ID/properties.
    _print_json(response)


def cmd_copy(args):
    client = SheetsClient()
    source = _parse_target(args.source)
    dest = _parse_second(args.dest, source)
    response = dispatch.do_copy(client, source, dest)
    _emit_mutation(dest, response, args.format == "json")


def cmd_move(args):
    client = SheetsClient()
    source = _parse_target(args.source)
    dest = _parse_second(args.dest, source)
    response = dispatch.do_move(client, source, dest)
    _emit_mutation(dest, response, args.format == "json")


# --------------------------------- auth -----------------------------------


_CREDENTIALS_SETUP = """
To set up authentication:

  1. Go to https://console.cloud.google.com/
  2. Create a project (or select an existing one)
  3. Enable the Google Sheets API and Google Drive API
  4. Go to APIs & Services > Credentials
  5. Create an OAuth 2.0 Client ID (Application type: Desktop app)
  6. Download the JSON and save it to:
       ~/.sheet-cli/credentials.json
  7. Run: sheet-cli auth
"""


def _find_llms_txt() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "llms.txt"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("llms.txt not found")


def cmd_help(_args=None):
    sys.stdout.write(_find_llms_txt().read_text())


def cmd_auth(args):
    try:
        get_credentials(force_reauth=True)
    except AuthenticationError as e:
        msg = str(e)
        print(f"Error: {msg}", file=sys.stderr)
        if "Credentials file not found" in msg:
            print(_CREDENTIALS_SETUP, file=sys.stderr)
        sys.exit(1)
    print("Authentication successful. Token cached at ~/.sheet-cli/token.json")


# --------------------------------- main -----------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="sheet-cli",
        description="Google Sheets & Drive — unified six-verb CLI.",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", dest="show_help",
        help="show full reference and exit",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    def add_format(p):
        p.add_argument("--format", choices=["text", "json"], default="text",
                       help="output format (default: text where applicable)")

    p_get = sub.add_parser("get", help="read cells / metadata / drive listing")
    p_get.add_argument("target", nargs="?", default="",
                       help="target string; omit for Drive-level listing")
    add_format(p_get)
    p_get.set_defaults(func=cmd_get)

    p_put = sub.add_parser("put", help="write cells (scalar sugar or stdin)")
    p_put.add_argument("target", help="target string (cell, range, or sheet)")
    p_put.add_argument("value", nargs="?", default=None,
                       help="optional scalar value; omit to read stdin")
    add_format(p_put)
    p_put.set_defaults(func=cmd_put)

    p_del = sub.add_parser("del", help="clear or delete target")
    p_del.add_argument("target", help="target string")
    add_format(p_del)
    p_del.set_defaults(func=cmd_del)

    p_new = sub.add_parser("new", help="create spreadsheet / sheet / row / column")
    p_new.add_argument("target", nargs="?", default="",
                       help="title or target string; omit for untitled spreadsheet")
    p_new.add_argument("--side", choices=["above", "below", "left", "right"],
                       default=None, help="for row/column targets")
    p_new.set_defaults(func=cmd_new)

    p_copy = sub.add_parser("copy", help="copy source to dest (server-side when possible)")
    p_copy.add_argument("source", help="source target")
    p_copy.add_argument("dest", help="destination target (components inherit from source)")
    add_format(p_copy)
    p_copy.set_defaults(func=cmd_copy)

    p_move = sub.add_parser("move", help="move source to dest (server-side when possible)")
    p_move.add_argument("source", help="source target")
    p_move.add_argument("dest", help="destination target (components inherit from source)")
    add_format(p_move)
    p_move.set_defaults(func=cmd_move)

    p_auth = sub.add_parser("auth", help="run OAuth flow and cache token")
    p_auth.set_defaults(func=cmd_auth)

    p_help = sub.add_parser("help", help="show full reference and exit")
    p_help.set_defaults(func=lambda _a: cmd_help())

    args = parser.parse_args()

    if args.show_help or args.command is None:
        cmd_help()
        return

    try:
        args.func(args)
    except GrammarError as e:
        print(f"grammar error: {e}", file=sys.stderr)
        sys.exit(2)
    except SheetsClientError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
