"""Shared Drive verb core.

Pure functions over a ``SheetsClient`` — called by both ``drive_cli.cli`` and
the MCP server, so the two surfaces stay in lockstep. Targets are plain Drive
file/folder IDs; the destination folder is always an optional argument.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from sheet_client import SheetsClient
from sheet_client.exceptions import SheetsAPIError, SheetsClientError

from . import mimes

FOLDER_MIME = "application/vnd.google-apps.folder"
SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
NATIVE_PREFIX = "application/vnd.google-apps."


def do_list(client: SheetsClient, folder: Optional[str] = None) -> List[dict]:
    """List Drive files at root, or directly inside ``folder``."""
    return client.list_files(folder_id=folder)


def do_copy(client: SheetsClient, file_id: str,
            folder: Optional[str] = None,
            name: Optional[str] = None) -> Dict[str, Any]:
    """Copy a Drive file or folder, optionally into ``folder``.

    The source mimeType decides the path: a folder is copied recursively, a
    spreadsheet via ``files.copy`` (sheet-shaped result), any other file via the
    generic ``files.copy``.
    """
    mime = client.get_file_mime(file_id)
    if mime == FOLDER_MIME:
        return client.copy_folder(file_id, new_title=name, parent_folder_id=folder)
    if mime == SPREADSHEET_MIME:
        return client.copy_spreadsheet(file_id, new_title=name, parent_folder_id=folder)
    return client.copy_file(file_id, new_title=name, parent_folder_id=folder)


def do_new(client: SheetsClient, kind: str, name: str,
           folder: Optional[str] = None) -> Dict[str, Any]:
    """Create a new ``folder`` or ``sheet`` (spreadsheet), optionally in ``folder``."""
    if kind == "folder":
        return client.create_folder(name, parent_folder_id=folder)
    if kind == "sheet":
        return client.create(name, parent_folder_id=folder)
    raise ValueError(f"unknown kind {kind!r} (expected 'folder' or 'sheet')")


def do_move(client: SheetsClient, file_id: str, folder: str,
            add: bool = False) -> Dict[str, Any]:
    """Move ``file_id`` into ``folder``.

    By default this *relocates* — adds ``folder`` and removes all current
    parents. With ``add=True`` it adds ``folder`` while keeping existing parents
    (Drive multi-parent).
    """
    if add:
        return client.update_parents(file_id, add=[folder])
    return client.update_parents(file_id, add=[folder],
                                 remove=client.get_parents(file_id))


def do_parents(client: SheetsClient, file_id: str) -> List[str]:
    """List the Drive folder IDs that contain ``file_id``."""
    return client.get_parents(file_id)


def do_upload(client: SheetsClient, path: str, target: Optional[str] = None, *,
              raw: bool = False, to: Optional[str] = None,
              name: Optional[str] = None,
              mime: Optional[str] = None) -> Dict[str, Any]:
    """Put a local file into Drive, converting to a Google type by default.

    ``target`` absent creates in My Drive root; a folder creates inside it;
    anything else replaces that file's bytes, keeping its ID, URL, sharing and
    comments.
    """
    if raw and to:
        raise ValueError("--raw and --to are mutually exclusive")
    if to is not None and to not in mimes.NATIVE_BY_ALIAS:
        raise ValueError(f"unknown --to {to!r} (expected doc, sheet, or slides)")
    if not os.path.isfile(path):
        raise ValueError(f"no such file: {path}")

    source = mime or mimes.source_mime(path)
    if source is None:
        raise ValueError(
            f"cannot guess a mimeType from the extension of {path}; pass --mime TYPE")

    if raw:
        convert_to = None
    elif to:
        convert_to = mimes.NATIVE_BY_ALIAS[to]
    else:
        convert_to = mimes.native_target(source)

    if target is None:
        return _upload_create(client, path, source, convert_to, name, None)

    target_mime = client.get_file_mime(target)
    if target_mime == FOLDER_MIME:
        return _upload_create(client, path, source, convert_to, name, target)

    # The existing file's type already fixes the stored format, so a --to
    # naming something else is a mistake rather than a no-op.
    if to and mimes.NATIVE_BY_ALIAS[to] != target_mime:
        raise ValueError(
            f"cannot --to {to}: {target} is already {target_mime}")

    result = client.update_file_content(target, path, source, name=name)
    return {"action": "replaced", **result}


def _upload_create(client: SheetsClient, path: str, source: str,
                   convert_to: Optional[str], name: Optional[str],
                   folder: Optional[str]) -> Dict[str, Any]:
    if name is None:
        base = os.path.basename(path)
        name = os.path.splitext(base)[0] if convert_to else base
    result = client.upload_file(path, source, name=name, convert_to=convert_to,
                                parent_folder_id=folder)
    return {"action": "created", **result}


def do_export(client: SheetsClient, file_id: str, out_path: str, *,
              mime: Optional[str] = None) -> Dict[str, Any]:
    """Write a Drive file to ``out_path``.

    A Google-native file is exported, with the type coming from ``--mime`` or
    ``out_path``'s extension. Any other file has nothing to convert, so it is a
    plain media download.
    """
    file_mime = client.get_file_mime(file_id)

    if file_mime.startswith(NATIVE_PREFIX):
        target = mime or mimes.export_mime(file_mime, out_path)
    else:
        if mime is not None:
            raise ValueError(
                f"{file_id} is {file_mime}, which needs no conversion; drop --mime")
        target = None

    try:
        result = client.export_file(file_id, out_path, export_mime=target)
    except SheetsAPIError as e:
        if "exportSizeLimitExceeded" in str(e):
            raise SheetsClientError(
                "Drive refuses to export a document over 10MB; download a .pdf "
                "from the Drive UI instead") from e
        raise

    return {
        "id": file_id,
        "name": result.get("name"),
        "mimeType": file_mime,
        "exported_as": target or file_mime,
        "path": out_path,
        "bytes": result.get("bytes"),
    }
