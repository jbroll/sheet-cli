"""drive-cli — Drive-native CLI (copy / new / move / list / parents).

Targets are plain Drive file/folder IDs. The destination folder is an optional
positional argument. Mutations print JSON; reads (list / parents) print text by
default, with ``--format=json`` for the raw API shape. Shares the
``sheet_client`` library and the cached OAuth token with sheet-cli.

    drive-cli list      [FOLDER]
    drive-cli copy      ID [FOLDER] [--name NAME]
    drive-cli new       folder|sheet NAME [FOLDER]
    drive-cli move      ID FOLDER [--add]
    drive-cli parents   ID
    drive-cli upload    FILE [ID] [--name NAME] [--raw | --to doc|sheet|slides] [--mime TYPE]
    drive-cli export    ID FILE [--mime TYPE]
    drive-cli inventory ROOT [-o MANIFEST]
    drive-cli plan      ROOT --to EMAIL [-o MANIFEST]
    drive-cli chown     MANIFEST --to EMAIL [--from OWNER]
    drive-cli accept    MANIFEST
    drive-cli auth

Every command takes ``--as EMAIL`` to pick which cached token to authenticate
with, since a transfer runs as each source owner and then as the new owner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from sheet_client import SheetsClient
from sheet_client.auth import cached_accounts, get_credentials, token_path_for
from sheet_client.exceptions import AuthenticationError, SheetsClientError

from . import ops, transfer


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _client(args) -> SheetsClient:
    """Client bound to the token for ``--as``, or the default token."""
    return SheetsClient(token_path=token_path_for(getattr(args, "account", None)))


# --------------------------------- verbs -----------------------------------


def cmd_list(args):
    client = _client(args)
    files = ops.do_list(client, folder=args.folder)
    if args.format == "json":
        _print_json(files)
        return
    for f in files:
        print(f"{f.get('id', '')}\t{f.get('name', '')}\t{f.get('mimeType', '')}")


def cmd_copy(args):
    client = _client(args)
    _print_json(ops.do_copy(client, args.id, folder=args.folder, name=args.name))


def cmd_new(args):
    client = _client(args)
    _print_json(ops.do_new(client, args.kind, args.name, folder=args.folder))


def cmd_move(args):
    client = _client(args)
    _print_json(ops.do_move(client, args.id, args.folder, add=args.add))


def cmd_parents(args):
    client = _client(args)
    parents = ops.do_parents(client, args.id)
    if args.format == "json":
        _print_json(parents)
        return
    for p in parents:
        print(p)


def cmd_upload(args):
    client = _client(args)
    _print_json(ops.do_upload(client, args.file, args.id, raw=args.raw,
                              to=args.to, name=args.name, mime=args.mime))


def cmd_export(args):
    client = _client(args)
    _print_json(ops.do_export(client, args.id, args.file, mime=args.mime))


def cmd_inventory(args):
    client = _client(args)
    manifest = transfer.build_manifest(client, args.root)
    if args.out:
        transfer.save_manifest(manifest, args.out)
        _print_json({"manifest": args.out, "root": manifest["root"],
                     "surveyed_by": manifest["surveyed_by"],
                     "nodes": len(manifest["nodes"]),
                     "owners": manifest["owners"]})
        return
    _print_json(manifest)


def cmd_plan(args):
    client = _client(args)
    if args.manifest:
        manifest = transfer.load_manifest(args.manifest)
    else:
        manifest = transfer.build_manifest(client, args.root)
        if args.out:
            transfer.save_manifest(manifest, args.out)
    plan = transfer.plan_transfer(manifest, args.to, authenticated=cached_accounts())
    if args.format == "json":
        _print_json(plan)
        return
    _print_plan(plan, manifest_path=args.manifest or args.out)


def _print_plan(plan: dict, manifest_path: Optional[str] = None) -> None:
    print(f"root      {plan['root']}")
    print(f"surveyed  {plan['surveyed_by']}")
    print(f"target    {plan['target']}")
    print(f"nodes     {plan['total_nodes']} "
          f"({plan['remaining']} to transfer, {plan['already_owned']} already owned)")

    if plan["owners"]:
        print("\nowners who must run chown (each authenticates as itself):")
        for owner in plan["owners"]:
            auth = "token cached" if owner["authenticated"] else "NEEDS LOGIN"
            done = f", {owner['done']} done" if owner["done"] else ""
            print(f"  {owner['email']:<40} {owner['remaining']:>5} items "
                  f"({owner['folders']} folders, {owner['files']} files{done})  {auth}")

    for label, items in plan["skipped"].items():
        if items:
            print(f"\ncannot transfer ({label.replace('_', ' ')}): {len(items)}")
            for item in items[:10]:
                print(f"  {item['id']}  {item['name']}")
            if len(items) > 10:
                print(f"  … {len(items) - 10} more")

    if plan["shortcuts"]:
        print(f"\nshortcuts: {len(plan['shortcuts'])} — Drive refuses ownership "
              "transfer on these; they stay with their current owner")

    print(f"\nup to {plan['api_calls_upper_bound']} Drive calls")

    if plan["logins_missing"]:
        print("\nrun first:")
        for email in plan["logins_missing"]:
            print(f"  drive-cli auth --as={email}")

    manifest = manifest_path or "MANIFEST"
    print("\nthen:")
    for owner in plan["owners"]:
        print(f"  drive-cli chown {manifest} --to={plan['target']} --as={owner['email']}")
    print(f"  drive-cli accept {manifest} --as={plan['target']}")
    print(f"  drive-cli move {plan['root']} DEST_FOLDER --as={plan['target']}")


def cmd_chown(args):
    client = _client(args)
    manifest = transfer.load_manifest(args.manifest)
    accept_client = None
    if args.accept:
        token = token_path_for(args.to)
        if not os.path.exists(token):
            raise SheetsClientError(
                f"--accept needs a cached token for {args.to}; "
                f"run: drive-cli auth --as={args.to}")
        accept_client = SheetsClient(token_path=token)
    save = lambda: transfer.save_manifest(manifest, args.manifest)
    summary = transfer.do_chown(client, manifest, args.to, from_owner=getattr(args, "from"),
                                mode=args.mode, notify=not args.no_notify,
                                dry_run=args.dry_run, pace=args.pace,
                                limit=args.limit, only=set(args.only) or None,
                                progress=_progress_sink(args),
                                checkpoint=None if args.dry_run else save,
                                checkpoint_every=args.checkpoint,
                                accept_client=accept_client)
    if not args.dry_run:
        save()
    _print_json(summary if args.verbose else _brief(summary))


def cmd_accept(args):
    client = _client(args)
    manifest = transfer.load_manifest(args.manifest)
    save = lambda: transfer.save_manifest(manifest, args.manifest)
    summary = transfer.do_accept(client, manifest, as_email=args.account,
                                 dry_run=args.dry_run, pace=args.pace,
                                 progress=_progress_sink(args),
                                 checkpoint=None if args.dry_run else save,
                                 checkpoint_every=args.checkpoint)
    if not args.dry_run:
        save()
    _print_json(summary if args.verbose else _brief(summary))


def _progress_sink(args):
    """Per-node progress goes to stderr, keeping stdout pure JSON."""
    if args.quiet:
        return None
    log = open(args.log, "a", buffering=1) if args.log else None

    def emit(line: str) -> None:
        print(line, file=sys.stderr, flush=True)
        if log:
            log.write(line + "\n")

    return emit


def _brief(summary: dict) -> dict:
    """Summary without the per-node results, plus whatever failed."""
    brief = {k: v for k, v in summary.items() if k != "results"}
    failures = [r for r in summary["results"] if r["state"].startswith("failed")]
    if failures:
        brief["failures"] = failures
    return brief


def cmd_auth(args):
    token_path = token_path_for(getattr(args, "account", None))
    try:
        get_credentials(token_path=token_path, force_reauth=True)
    except AuthenticationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Authentication successful. Token cached at "
          f"{token_path or '~/.sheet-cli/token.json'}")


# --------------------------------- main -----------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drive-cli",
        description="Google Drive — file/folder copy, create, move, list, and ownership transfer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_account(p):
        p.add_argument("--as", dest="account", default=None, metavar="EMAIL",
                       help="authenticate as this account "
                            "(token at ~/.sheet-cli/token-EMAIL.json)")

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

    p_upload = sub.add_parser("upload", help="upload a local file into Drive")
    p_upload.add_argument("file", help="local file to upload")
    p_upload.add_argument("id", nargs="?", default=None,
                          help="destination folder ID, or a file ID whose "
                               "content to replace; omit for My Drive root")
    p_upload.add_argument("--name", default=None,
                          help="name for the Drive file (default: the "
                               "basename, without extension when converting)")
    convert = p_upload.add_mutually_exclusive_group()
    convert.add_argument("--raw", action="store_true",
                         help="store the bytes as-is, no Google conversion")
    convert.add_argument("--to", choices=["doc", "sheet", "slides"], default=None,
                         help="force conversion to this Google type")
    p_upload.add_argument("--mime", default=None, metavar="TYPE",
                          help="source mimeType, when the extension is "
                               "missing or wrong")
    p_upload.set_defaults(func=cmd_upload)

    p_export = sub.add_parser("export",
                              help="write a Drive file out as a local file")
    p_export.add_argument("id", help="Drive file ID")
    p_export.add_argument("file", help="local path to write")
    p_export.add_argument("--mime", default=None, metavar="TYPE",
                          help="export mimeType, overriding the guess from "
                               "FILE's extension")
    p_export.set_defaults(func=cmd_export)

    p_inv = sub.add_parser("inventory",
                           help="walk a folder tree, recording every node and its owner")
    p_inv.add_argument("root", help="folder (or file) ID to inventory")
    p_inv.add_argument("-o", "--out", default=None, metavar="MANIFEST",
                       help="write the manifest to this file (default: stdout)")
    p_inv.set_defaults(func=cmd_inventory)

    p_plan = sub.add_parser("plan",
                            help="report which owners must act to transfer a tree")
    p_plan.add_argument("root", nargs="?", default=None,
                        help="folder ID to walk; omit when using --manifest")
    p_plan.add_argument("--to", required=True, metavar="EMAIL",
                        help="the intended new owner")
    p_plan.add_argument("-m", "--manifest", default=None,
                        help="plan from an existing manifest instead of walking")
    p_plan.add_argument("-o", "--out", default=None, metavar="MANIFEST",
                        help="save the walk as a manifest for the chown pass")
    add_format(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_chown = sub.add_parser("chown",
                             help="transfer one owner's files in a manifest to a new owner")
    p_chown.add_argument("manifest", help="manifest from `inventory` (updated in place)")
    p_chown.add_argument("--to", required=True, metavar="EMAIL",
                         help="the new owner")
    p_chown.add_argument("--from", default=None, metavar="EMAIL",
                         help="only transfer files owned by this account "
                              "(default: the authenticated account)")
    p_chown.add_argument("--mode", choices=["auto", "direct", "pending"], default="auto",
                         help="auto: one-call Workspace transfer, falling back to the "
                              "consumer pending-owner flow (default)")
    p_chown.add_argument("--no-notify", action="store_true",
                         help="skip the email to the prospective owner")
    p_chown.add_argument("--accept", action="store_true",
                         help="accept each offer immediately as --to (one pass, "
                              "files change hands as they go)")
    p_chown.add_argument("--limit", type=int, default=None, metavar="N",
                         help="stop after N nodes (smoke-test a large slice)")
    p_chown.add_argument("--only", action="append", default=[], metavar="ID",
                         help="transfer just this node; repeatable")
    p_chown.set_defaults(func=cmd_chown)

    p_accept = sub.add_parser("accept",
                              help="accept every pending transfer in a manifest")
    p_accept.add_argument("manifest", help="manifest from `chown` (updated in place)")
    p_accept.set_defaults(func=cmd_accept)

    for p in (p_chown, p_accept):
        p.add_argument("--quiet", action="store_true",
                       help="suppress the per-node progress lines on stderr")
        p.add_argument("--log", default=None, metavar="PATH",
                       help="also append progress lines to this file")
        p.add_argument("--checkpoint", type=int, default=25, metavar="N",
                       help="save the manifest every N nodes (default 25)")
        p.add_argument("--pace", type=float, default=0.0, metavar="SECONDS",
                       help="sleep between nodes to stay under Drive's rate limits")
        p.add_argument("--dry-run", action="store_true",
                       help="report what would change without calling Drive")
        p.add_argument("--verbose", action="store_true",
                       help="include the per-node results")

    p_auth = sub.add_parser("auth", help="run OAuth flow and cache token")
    p_auth.set_defaults(func=cmd_auth)

    for p in (p_list, p_copy, p_new, p_move, p_parents, p_upload, p_export,
              p_inv, p_plan, p_chown, p_accept, p_auth):
        add_account(p)

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
