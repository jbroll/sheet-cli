"""drive-cli — Drive-native CLI (copy / new / move / list / parents).

Targets are plain Drive file/folder IDs. The destination folder is an optional
positional argument. Mutations print JSON; reads (list / parents) print text by
default, with ``--format=json`` for the raw API shape. Shares the
``sheet_client`` library and the cached OAuth token with sheet-cli.

    drive-cli list    [FOLDER]
    drive-cli copy    ID [FOLDER] [--name NAME]
    drive-cli new     folder|sheet NAME [FOLDER]
    drive-cli move    ID FOLDER [--add]
    drive-cli parents ID
    drive-cli auth
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sheet_client import SheetsClient
from sheet_client.auth import get_credentials
from sheet_client.exceptions import AuthenticationError, SheetsClientError

from . import ops


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


# --------------------------------- verbs -----------------------------------


def cmd_list(args):
    client = SheetsClient()
    files = ops.do_list(client, folder=args.folder)
    if args.format == "json":
        _print_json(files)
        return
    for f in files:
        print(f"{f.get('id', '')}\t{f.get('name', '')}\t{f.get('mimeType', '')}")


def cmd_copy(args):
    client = SheetsClient()
    _print_json(ops.do_copy(client, args.id, folder=args.folder, name=args.name))


def cmd_new(args):
    client = SheetsClient()
    _print_json(ops.do_new(client, args.kind, args.name, folder=args.folder))


def cmd_move(args):
    client = SheetsClient()
    _print_json(ops.do_move(client, args.id, args.folder, add=args.add))


def cmd_parents(args):
    client = SheetsClient()
    parents = ops.do_parents(client, args.id)
    if args.format == "json":
        _print_json(parents)
        return
    for p in parents:
        print(p)


def cmd_auth(_args):
    try:
        get_credentials(force_reauth=True)
    except AuthenticationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Authentication successful. Token cached at ~/.sheet-cli/token.json")


# --------------------------------- main -----------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drive-cli",
        description="Google Drive — file/folder copy, create, move, list.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_format(p):
        p.add_argument("--format", choices=["text", "json"], default="text",
                       help="output format (default: text for list/parents)")

    p_list = sub.add_parser("list", help="list Drive files (root or in a folder)")
    p_list.add_argument("folder", nargs="?", default=None,
                        help="folder ID to list inside; omit for root")
    add_format(p_list)
    p_list.set_defaults(func=cmd_list)

    p_copy = sub.add_parser("copy", help="copy a file or folder (folders are recursive)")
    p_copy.add_argument("id", help="Drive file/folder ID to copy")
    p_copy.add_argument("folder", nargs="?", default=None,
                        help="destination folder ID; omit for My Drive root")
    p_copy.add_argument("--name", default=None, help="name for the copy")
    p_copy.set_defaults(func=cmd_copy)

    p_new = sub.add_parser("new", help="create a folder or spreadsheet")
    p_new.add_argument("kind", choices=["folder", "sheet"], help="what to create")
    p_new.add_argument("name", help="name for the new resource")
    p_new.add_argument("folder", nargs="?", default=None,
                       help="parent folder ID; omit for My Drive root")
    p_new.set_defaults(func=cmd_new)

    p_move = sub.add_parser("move", help="move a file/folder into a folder")
    p_move.add_argument("id", help="Drive file/folder ID to move")
    p_move.add_argument("folder", help="destination folder ID")
    p_move.add_argument("--add", action="store_true",
                        help="add to folder, keeping existing parents (multi-parent)")
    p_move.set_defaults(func=cmd_move)

    p_parents = sub.add_parser("parents", help="list the folders containing a file")
    p_parents.add_argument("id", help="Drive file/folder ID")
    add_format(p_parents)
    p_parents.set_defaults(func=cmd_parents)

    p_auth = sub.add_parser("auth", help="run OAuth flow and cache token")
    p_auth.set_defaults(func=cmd_auth)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    except SheetsClientError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
