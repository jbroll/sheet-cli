"""Shared Drive verb core.

Pure functions over a ``SheetsClient`` — called by both ``drive_cli.cli`` and
the MCP server, so the two surfaces stay in lockstep. Targets are plain Drive
file/folder IDs; the destination folder is always an optional argument.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sheet_client import SheetsClient

FOLDER_MIME = "application/vnd.google-apps.folder"
SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"


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
