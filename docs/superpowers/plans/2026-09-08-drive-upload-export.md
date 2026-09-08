# drive-cli upload / export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `upload` and `export` verbs to `drive-cli` so local files can be put into Drive (converting to Google types) and pulled back out.

**Architecture:** A pure-data module `src/drive_cli/mimes.py` maps extensions to mimeTypes and Google-native types to export mimeTypes. Two verb cores `do_upload` / `do_export` in `src/drive_cli/ops.py` branch on the target's mimeType and call three new thin wrappers in `sheet_client/client.py` that keep `googleapiclient` media imports out of `ops.py`. `drive_cli/cli.py` adds two subparsers.

**Tech Stack:** Python 3, `google-api-python-client` (`MediaFileUpload`, `MediaIoBaseDownload`), `argparse`, `pytest`, `unittest.mock`.

## Global Constraints

- Drive API only: `files.create`, `files.update`, `files.export`, `files.get`. No Docs API call of any kind.
- No change to `SCOPES` in `src/sheet_client/auth.py`. The cached token's `https://www.googleapis.com/auth/drive` scope already covers all four calls.
- No MCP tools registered for these verbs. `do_upload` / `do_export` live in `ops.py` so the MCP server can pick them up later.
- `src/drive_cli/mimes.py` imports nothing from `sheet_client` or `googleapiclient`.
- No recursive folder upload — `upload` takes one file. No sync or change detection.
- No integration tests against real Drive.
- Exit codes come from the existing handlers in `drive_cli/cli.py:main()`: `ValueError` → 2, `SheetsClientError` → 1.
- Uploads pass `resumable=True`. Downloads use `MediaIoBaseDownload` in chunks.
- Docs land in the same commit as the code they describe.

## File Structure

- **Create** `src/drive_cli/mimes.py` — three tables, three functions, offline-testable.
- **Create** `test/test_mimes.py` — the table logic, no mocks.
- **Modify** `src/sheet_client/client.py` — `upload_file`, `update_file_content`, `export_file` after `copy_file`.
- **Modify** `test/test_client.py` — a `TestDriveTransferPrimitives` class.
- **Modify** `src/drive_cli/ops.py` — `do_upload`, `do_export`, plus `_upload_create` helper.
- **Modify** `test/test_drive_ops.py` — `TestDoUpload`, `TestDoExport`.
- **Modify** `src/drive_cli/cli.py` — `cmd_upload`, `cmd_export`, two subparsers, docstring.
- **Modify** `test/test_drive_cli.py` — `TestUpload`, `TestExport`.
- **Modify** `README.md`, `CLAUDE.md`, `API.md`.

---

### Task 1: `mimes.py` — extension and export tables

**Files:**
- Create: `src/drive_cli/mimes.py`
- Test: `test/test_mimes.py`

**Model:** `haiku` — the complete code for both files is given below; this is transcription plus a test run.

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `DOC_MIME`, `SHEET_MIME`, `SLIDES_MIME` — the three `application/vnd.google-apps.*` constants.
  - `NATIVE_BY_ALIAS: Dict[str, str]` — `{"doc": DOC_MIME, "sheet": SHEET_MIME, "slides": SLIDES_MIME}`.
  - `EXT_TO_MIME: Dict[str, str]`, `MIME_TO_NATIVE: Dict[str, str]`, `NATIVE_EXPORTS: Dict[str, Dict[str, str]]`.
  - `source_mime(path: str) -> Optional[str]`
  - `native_target(source: str) -> Optional[str]`
  - `export_mime(file_mime: str, out_path: str) -> str` — raises `ValueError`.

- [ ] **Step 1: Write the failing test**

Create `test/test_mimes.py`:

```python
"""Tests for drive_cli.mimes — extension and export mimeType tables (offline)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from drive_cli import mimes

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class TestSourceMime:
    def test_known_extension(self):
        assert mimes.source_mime("flyer.docx") == DOCX
        assert mimes.source_mime("data.csv") == "text/csv"
        assert mimes.source_mime("deck.pptx") == PPTX

    def test_extension_is_case_insensitive(self):
        assert mimes.source_mime("FLYER.DOCX") == DOCX

    def test_full_path_uses_only_the_extension(self):
        assert mimes.source_mime("/a/b/c/notes.txt") == "text/plain"

    def test_unknown_extension_is_none(self):
        assert mimes.source_mime("archive.wat") is None

    def test_extensionless_path_is_none(self):
        assert mimes.source_mime("data") is None


class TestNativeTarget:
    def test_word_processing_converts_to_doc(self):
        assert mimes.native_target(DOCX) == mimes.DOC_MIME
        assert mimes.native_target("text/plain") == mimes.DOC_MIME
        assert mimes.native_target("text/markdown") == mimes.DOC_MIME

    def test_spreadsheet_converts_to_sheet(self):
        assert mimes.native_target(XLSX) == mimes.SHEET_MIME
        assert mimes.native_target("text/csv") == mimes.SHEET_MIME

    def test_presentation_converts_to_slides(self):
        assert mimes.native_target(PPTX) == mimes.SLIDES_MIME

    def test_no_equivalent_is_none(self):
        assert mimes.native_target("application/pdf") is None
        assert mimes.native_target("image/png") is None


class TestExportMime:
    def test_doc_to_pdf(self):
        assert mimes.export_mime(mimes.DOC_MIME, "out.pdf") == "application/pdf"

    def test_doc_to_docx(self):
        assert mimes.export_mime(mimes.DOC_MIME, "out.docx") == DOCX

    def test_sheet_to_csv(self):
        assert mimes.export_mime(mimes.SHEET_MIME, "out.csv") == "text/csv"

    def test_slides_to_pptx(self):
        assert mimes.export_mime(mimes.SLIDES_MIME, "out.pptx") == PPTX

    def test_extension_is_case_insensitive(self):
        assert mimes.export_mime(mimes.DOC_MIME, "OUT.PDF") == "application/pdf"

    def test_extension_invalid_for_the_type_lists_the_valid_ones(self):
        with pytest.raises(ValueError, match="epub"):
            mimes.export_mime(mimes.DOC_MIME, "out.xlsx")

    def test_extensionless_output_raises(self):
        with pytest.raises(ValueError):
            mimes.export_mime(mimes.DOC_MIME, "out")

    def test_non_native_type_raises(self):
        with pytest.raises(ValueError, match="cannot export"):
            mimes.export_mime("application/pdf", "out.pdf")

    def test_native_type_with_no_exports_raises(self):
        with pytest.raises(ValueError, match="cannot export"):
            mimes.export_mime("application/vnd.google-apps.folder", "out.pdf")


class TestAliases:
    def test_three_aliases(self):
        assert mimes.NATIVE_BY_ALIAS == {
            "doc": mimes.DOC_MIME,
            "sheet": mimes.SHEET_MIME,
            "slides": mimes.SLIDES_MIME,
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_mimes.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'drive_cli.mimes'` (or `ImportError: cannot import name 'mimes'`).

- [ ] **Step 3: Write the implementation**

Create `src/drive_cli/mimes.py`:

```python
"""Extension and mimeType tables for ``drive-cli upload`` / ``export``.

Pure data with no Drive or ``googleapiclient`` import, so the mapping is
testable offline.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SLIDES_MIME = "application/vnd.google-apps.presentation"

NATIVE_BY_ALIAS: Dict[str, str] = {
    "doc": DOC_MIME,
    "sheet": SHEET_MIME,
    "slides": SLIDES_MIME,
}

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_ODT = "application/vnd.oasis.opendocument.text"
_ODS = "application/vnd.oasis.opendocument.spreadsheet"
_ODP = "application/vnd.oasis.opendocument.presentation"

EXT_TO_MIME: Dict[str, str] = {
    # word processing
    ".docx": _DOCX,
    ".doc": "application/msword",
    ".odt": _ODT,
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    # spreadsheet
    ".xlsx": _XLSX,
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".ods": _ODS,
    # presentation
    ".pptx": _PPTX,
    ".ppt": "application/vnd.ms-powerpoint",
    ".odp": _ODP,
    # no Google equivalent — uploaded as-is
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".zip": "application/zip",
    ".json": "application/json",
}

# Source types absent from this table have no Google equivalent and upload raw.
MIME_TO_NATIVE: Dict[str, str] = {
    _DOCX: DOC_MIME,
    "application/msword": DOC_MIME,
    _ODT: DOC_MIME,
    "application/rtf": DOC_MIME,
    "text/plain": DOC_MIME,
    "text/html": DOC_MIME,
    "text/markdown": DOC_MIME,
    _XLSX: SHEET_MIME,
    "application/vnd.ms-excel": SHEET_MIME,
    "text/csv": SHEET_MIME,
    "text/tab-separated-values": SHEET_MIME,
    _ODS: SHEET_MIME,
    _PPTX: SLIDES_MIME,
    "application/vnd.ms-powerpoint": SLIDES_MIME,
    _ODP: SLIDES_MIME,
}

NATIVE_EXPORTS: Dict[str, Dict[str, str]] = {
    DOC_MIME: {
        "pdf": "application/pdf",
        "docx": _DOCX,
        "odt": _ODT,
        "rtf": "application/rtf",
        "txt": "text/plain",
        "html": "text/html",
        "epub": "application/epub+zip",
    },
    SHEET_MIME: {
        "pdf": "application/pdf",
        "xlsx": _XLSX,
        "ods": _ODS,
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "zip": "application/zip",
    },
    SLIDES_MIME: {
        "pdf": "application/pdf",
        "pptx": _PPTX,
        "odp": _ODP,
        "txt": "text/plain",
    },
}


def source_mime(path: str) -> Optional[str]:
    """The mimeType to upload ``path`` as, from its extension."""
    return EXT_TO_MIME.get(os.path.splitext(path)[1].lower())


def native_target(source: str) -> Optional[str]:
    """The Google-native type ``source`` converts to, or ``None``."""
    return MIME_TO_NATIVE.get(source)


def export_mime(file_mime: str, out_path: str) -> str:
    """The export mimeType for a ``file_mime`` file written to ``out_path``."""
    table = NATIVE_EXPORTS.get(file_mime)
    if table is None:
        raise ValueError(f"cannot export {file_mime}")
    ext = os.path.splitext(out_path)[1].lower().lstrip(".")
    if ext not in table:
        raise ValueError(
            f"cannot export {file_mime} as {'.' + ext if ext else 'a file with no extension'}; "
            f"valid extensions: {', '.join(sorted(table))}")
    return table[ext]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_mimes.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/john/src/sheet-cli
git add src/drive_cli/mimes.py test/test_mimes.py
git commit -m "feat(drive): mimeType tables for upload/export"
```

---

### Task 2: client media wrappers

**Files:**
- Modify: `src/sheet_client/client.py` (imports at the top; three methods inserted after `copy_file`, which ends at line 765)
- Test: `test/test_client.py` (new class appended after `TestDriveCopyPrimitives`)

**Model:** `sonnet` — touches an existing 1000-line module and has to place methods and imports in the right spot alongside existing patterns.

**Interfaces:**
- Consumes: `self.drive`, `self._execute_with_retry`, `SheetsAPIError` — all already present in `client.py`.
- Produces, as methods on `SheetsClient`:
  - `upload_file(path: str, source_mime: str, *, name: str, convert_to: Optional[str] = None, parent_folder_id: Optional[str] = None) -> dict` → `{'id', 'name', 'mimeType', 'webViewLink', 'parents'}`
  - `update_file_content(file_id: str, path: str, source_mime: str, *, name: Optional[str] = None) -> dict` → same keys
  - `export_file(file_id: str, out_path: str, export_mime: Optional[str] = None) -> dict` → `{'id', 'name', 'mimeType', 'bytes'}`

Note on retries: the upload calls go through `_execute_with_retry` like every other call. The download loop cannot, because `MediaIoBaseDownload` owns its own request cycle, so it uses that class's built-in `next_chunk(num_retries=5)` for the same 429/5xx backoff, and its `HttpError` is converted to `SheetsAPIError` so callers see one exception type.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_client.py`:

```python
class TestDriveTransferPrimitives:
    """upload_file / update_file_content / export_file."""

    def _make_client(self):
        from unittest.mock import MagicMock
        from sheet_client.client import SheetsClient

        mock_drive = MagicMock()
        client = SheetsClient.__new__(SheetsClient)
        client.drive = mock_drive
        client._execute_with_retry = MagicMock()
        return client, mock_drive

    # ------------------------------- upload_file -----------------------------

    def test_upload_file_converts_and_places_in_folder(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEW", "name": "flyer",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://docs.google.com/document/d/NEW",
            "parents": ["FOLDER"],
        }
        src = tmp_path / "flyer.docx"
        src.write_bytes(b"x")
        with patch("sheet_client.client.MediaFileUpload") as media:
            result = client.upload_file(
                str(src), "application/msword", name="flyer",
                convert_to="application/vnd.google-apps.document",
                parent_folder_id="FOLDER")
        assert media.call_args[1]["resumable"] is True
        assert media.call_args[1]["mimetype"] == "application/msword"
        body = mock_drive.files.return_value.create.call_args[1]["body"]
        assert body["name"] == "flyer"
        assert body["parents"] == ["FOLDER"]
        assert body["mimeType"] == "application/vnd.google-apps.document"
        assert result["id"] == "NEW"
        assert result["webViewLink"].endswith("NEW")

    def test_upload_file_raw_omits_mimetype_and_parents(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "NEW", "name": "flyer.docx", "mimeType": "application/msword",
            "webViewLink": "u", "parents": [],
        }
        src = tmp_path / "flyer.docx"
        src.write_bytes(b"x")
        with patch("sheet_client.client.MediaFileUpload"):
            client.upload_file(str(src), "application/msword", name="flyer.docx")
        body = mock_drive.files.return_value.create.call_args[1]["body"]
        assert "mimeType" not in body
        assert "parents" not in body

    # --------------------------- update_file_content -------------------------

    def test_update_file_content_keeps_the_id_and_omits_an_absent_name(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "DOC1", "name": "Flyer",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "u", "parents": ["FOLDER"],
        }
        src = tmp_path / "flyer.docx"
        src.write_bytes(b"x")
        with patch("sheet_client.client.MediaFileUpload"):
            result = client.update_file_content(
                "DOC1", str(src), "application/msword")
        kwargs = mock_drive.files.return_value.update.call_args[1]
        assert kwargs["fileId"] == "DOC1"
        assert "name" not in kwargs["body"]
        assert result["id"] == "DOC1"

    def test_update_file_content_renames_when_given_a_name(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "id": "DOC1", "name": "Renamed", "mimeType": "x",
            "webViewLink": "u", "parents": [],
        }
        src = tmp_path / "flyer.docx"
        src.write_bytes(b"x")
        with patch("sheet_client.client.MediaFileUpload"):
            client.update_file_content("DOC1", str(src), "application/msword",
                                       name="Renamed")
        body = mock_drive.files.return_value.update.call_args[1]["body"]
        assert body["name"] == "Renamed"

    # ------------------------------- export_file -----------------------------

    def _fake_downloader(self, payload):
        """Patch MediaIoBaseDownload so next_chunk writes payload and finishes."""
        from unittest.mock import MagicMock

        def factory(fh, request):
            downloader = MagicMock()

            def next_chunk(num_retries=0):
                fh.write(payload)
                return (MagicMock(), True)

            downloader.next_chunk.side_effect = next_chunk
            return downloader

        return factory

    def test_export_file_uses_export_media_and_reports_bytes(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "name": "Flyer", "mimeType": "application/vnd.google-apps.document"}
        out = tmp_path / "out.pdf"
        with patch("sheet_client.client.MediaIoBaseDownload",
                   side_effect=self._fake_downloader(b"PDFDATA")):
            result = client.export_file("DOC1", str(out),
                                        export_mime="application/pdf")
        kwargs = mock_drive.files.return_value.export_media.call_args[1]
        assert kwargs["fileId"] == "DOC1"
        assert kwargs["mimeType"] == "application/pdf"
        assert out.read_bytes() == b"PDFDATA"
        assert result == {"id": "DOC1", "name": "Flyer",
                          "mimeType": "application/vnd.google-apps.document",
                          "bytes": 7}

    def test_export_file_without_export_mime_downloads_media(self, tmp_path):
        from unittest.mock import patch
        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {
            "name": "scan.pdf", "mimeType": "application/pdf"}
        out = tmp_path / "out.pdf"
        with patch("sheet_client.client.MediaIoBaseDownload",
                   side_effect=self._fake_downloader(b"RAW")):
            client.export_file("PDF1", str(out))
        mock_drive.files.return_value.export_media.assert_not_called()
        assert mock_drive.files.return_value.get_media.call_args[1]["fileId"] == "PDF1"

    def test_export_file_converts_http_error_to_sheets_api_error(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from googleapiclient.errors import HttpError
        from sheet_client.exceptions import SheetsAPIError

        client, mock_drive = self._make_client()
        client._execute_with_retry.return_value = {"name": "Big", "mimeType": "m"}
        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b'{"error": {"errors": '
                                b'[{"reason": "exportSizeLimitExceeded"}]}}')

        def factory(fh, request):
            downloader = MagicMock()
            downloader.next_chunk.side_effect = error
            return downloader

        out = tmp_path / "out.pdf"
        with patch("sheet_client.client.MediaIoBaseDownload", side_effect=factory):
            with pytest.raises(SheetsAPIError, match="exportSizeLimitExceeded"):
                client.export_file("DOC1", str(out), export_mime="application/pdf")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_client.py::TestDriveTransferPrimitives -v`
Expected: FAIL — `AttributeError: 'SheetsClient' object has no attribute 'upload_file'`, and `AttributeError: <module 'sheet_client.client'> does not have the attribute 'MediaFileUpload'`.

- [ ] **Step 3: Add the imports**

In `src/sheet_client/client.py`, the top of the file currently reads:

```python
import random
import time
from enum import IntFlag
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
```

Change it to:

```python
import io
import os
import random
import time
from enum import IntFlag
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
```

(Keep any lines already present that are not shown here, such as the module docstring and the `from .auth import get_credentials` / `from .exceptions import ...` lines below.)

- [ ] **Step 4: Write the three methods**

Insert into `src/sheet_client/client.py` immediately after `copy_file` ends (the `}` closing its return dict, currently line 765) and before `def copy_folder`:

```python
    def upload_file(self, path: str, source_mime: str, *, name: str,
                    convert_to: Optional[str] = None,
                    parent_folder_id: Optional[str] = None) -> dict:
        """Create a Drive file from local bytes, optionally converting it.

        Args:
            path: Local file to upload.
            source_mime: The mimeType of the local bytes.
            name: Name for the new Drive file.
            convert_to: A ``application/vnd.google-apps.*`` type to convert to.
                When omitted the bytes are stored as-is.
            parent_folder_id: Drive folder to create it in. When omitted, the
                file lands in the user's My Drive root.

        Returns:
            ``{'id', 'name', 'mimeType', 'webViewLink', 'parents'}``.
        """
        body: Dict[str, Any] = {'name': name}
        if parent_folder_id:
            body['parents'] = [parent_folder_id]
        if convert_to:
            body['mimeType'] = convert_to

        media = MediaFileUpload(path, mimetype=source_mime, resumable=True)
        request = self.drive.files().create(
            body=body,
            media_body=media,
            fields='id,name,mimeType,webViewLink,parents',
        )
        return self._file_result(self._execute_with_retry(request))

    def update_file_content(self, file_id: str, path: str, source_mime: str, *,
                            name: Optional[str] = None) -> dict:
        """Replace an existing Drive file's bytes, keeping its ID.

        The file keeps its URL, sharing and comments; Drive records a new
        revision. The stored format is fixed by the existing file, so there is
        no conversion argument.

        Args:
            file_id: The Drive file to overwrite.
            path: Local file supplying the new bytes.
            source_mime: The mimeType of those bytes.
            name: Rename the file as well. When omitted the name is unchanged.

        Returns:
            ``{'id', 'name', 'mimeType', 'webViewLink', 'parents'}``.
        """
        body: Dict[str, Any] = {'name': name} if name else {}
        media = MediaFileUpload(path, mimetype=source_mime, resumable=True)
        request = self.drive.files().update(
            fileId=file_id,
            body=body,
            media_body=media,
            fields='id,name,mimeType,webViewLink,parents',
        )
        return self._file_result(self._execute_with_retry(request))

    def export_file(self, file_id: str, out_path: str,
                    export_mime: Optional[str] = None) -> dict:
        """Write a Drive file to ``out_path``.

        With ``export_mime`` this is ``files.export`` — converting a
        Google-native document to that type. Without it, a plain
        ``files.get`` media download.

        ``MediaIoBaseDownload`` owns its own request cycle, so the chunk loop
        does its 429/5xx backoff through ``num_retries`` rather than
        :meth:`_execute_with_retry`. Its ``HttpError`` is converted so callers
        see one exception type.

        Returns:
            ``{'id', 'name', 'mimeType', 'bytes'}`` — ``mimeType`` is the
            Drive file's type, not the exported one.
        """
        meta = self._execute_with_retry(
            self.drive.files().get(fileId=file_id, fields='name,mimeType'))

        if export_mime:
            request = self.drive.files().export_media(
                fileId=file_id, mimeType=export_mime)
        else:
            request = self.drive.files().get_media(fileId=file_id)

        with io.FileIO(out_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                try:
                    _status, done = downloader.next_chunk(num_retries=5)
                except HttpError as e:
                    raise SheetsAPIError(
                        f"API error {e.resp.status}: {str(e)}",
                        status_code=e.resp.status,
                        response=e.error_details if hasattr(e, 'error_details') else None
                    )

        return {
            'id': file_id,
            'name': meta.get('name'),
            'mimeType': meta.get('mimeType'),
            'bytes': os.path.getsize(out_path),
        }

    def _file_result(self, response: dict) -> dict:
        """Shape a ``files`` response into the upload/replace result dict."""
        return {
            'id': response['id'],
            'name': response.get('name'),
            'mimeType': response.get('mimeType'),
            'webViewLink': response.get('webViewLink'),
            'parents': response.get('parents', []),
        }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_client.py -v`
Expected: all tests PASS, including the nine in `TestDriveTransferPrimitives`.

- [ ] **Step 6: Commit**

```bash
cd /home/john/src/sheet-cli
git add src/sheet_client/client.py test/test_client.py
git commit -m "feat(client): upload_file, update_file_content, export_file"
```

---

### Task 3: `ops.do_upload`

**Files:**
- Modify: `src/drive_cli/ops.py`
- Test: `test/test_drive_ops.py`

**Model:** `sonnet` — branching logic with several error paths that must line up with the spec's exit-code table.

**Interfaces:**
- Consumes: `mimes.source_mime`, `mimes.native_target`, `mimes.NATIVE_BY_ALIAS`, `mimes.DOC_MIME/SHEET_MIME/SLIDES_MIME` (Task 1); `client.get_file_mime`, `client.upload_file`, `client.update_file_content` (Task 2); the existing `FOLDER_MIME` constant in `ops.py`.
- Produces: `do_upload(client, path, target=None, *, raw=False, to=None, name=None, mime=None) -> Dict[str, Any]` returning `{"action": "created"|"replaced", "id", "name", "mimeType", "webViewLink", "parents"}`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_drive_ops.py`, before the `if __name__` block:

```python
# -------------------------------- do_upload --------------------------------

DOC_MIME = "application/vnd.google-apps.document"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def docx(tmp_path):
    path = tmp_path / "flyer.docx"
    path.write_bytes(b"bytes")
    return str(path)


class TestDoUpload:
    def _uploaded(self, client, **over):
        result = {"id": "NEW", "name": "flyer", "mimeType": DOC_MIME,
                  "webViewLink": "https://docs.google.com/document/d/NEW",
                  "parents": []}
        result.update(over)
        client.upload_file.return_value = result
        client.update_file_content.return_value = result
        return result

    def test_no_target_creates_at_root_converting(self, client, docx):
        self._uploaded(client)
        result = ops.do_upload(client, docx)
        client.get_file_mime.assert_not_called()
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer", convert_to=DOC_MIME,
            parent_folder_id=None)
        assert result["action"] == "created"
        assert result["id"] == "NEW"

    def test_folder_target_creates_inside_it(self, client, docx):
        self._uploaded(client)
        client.get_file_mime.return_value = FOLDER_MIME
        ops.do_upload(client, docx, "FOLDER1")
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer", convert_to=DOC_MIME,
            parent_folder_id="FOLDER1")

    def test_file_target_replaces_its_content(self, client, docx):
        self._uploaded(client, id="DOC1")
        client.get_file_mime.return_value = DOC_MIME
        result = ops.do_upload(client, docx, "DOC1")
        client.update_file_content.assert_called_once_with(
            "DOC1", docx, DOCX, name=None)
        client.upload_file.assert_not_called()
        assert result["action"] == "replaced"
        assert result["id"] == "DOC1"

    def test_raw_skips_conversion_and_keeps_the_extension_in_the_name(
            self, client, docx):
        self._uploaded(client)
        ops.do_upload(client, docx, raw=True)
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer.docx", convert_to=None,
            parent_folder_id=None)

    def test_to_forces_a_native_type(self, client, tmp_path):
        self._uploaded(client)
        path = str(tmp_path / "notes.txt")
        open(path, "w").write("hi")
        ops.do_upload(client, path, to="doc")
        client.upload_file.assert_called_once_with(
            path, "text/plain", name="notes", convert_to=DOC_MIME,
            parent_folder_id=None)

    def test_explicit_name_wins(self, client, docx):
        self._uploaded(client)
        ops.do_upload(client, docx, name="Q3 Flyer")
        assert client.upload_file.call_args[1]["name"] == "Q3 Flyer"

    def test_mime_overrides_the_extension_guess(self, client, tmp_path):
        self._uploaded(client)
        path = str(tmp_path / "data")
        open(path, "w").write("a,b")
        ops.do_upload(client, path, mime="text/csv")
        assert client.upload_file.call_args[0][1] == "text/csv"
        assert client.upload_file.call_args[1]["convert_to"] == \
            "application/vnd.google-apps.spreadsheet"

    def test_unknown_extension_without_mime_raises(self, client, tmp_path):
        path = str(tmp_path / "data")
        open(path, "w").write("x")
        with pytest.raises(ValueError, match="--mime"):
            ops.do_upload(client, path)

    def test_missing_file_raises(self, client, tmp_path):
        with pytest.raises(ValueError, match="no such file"):
            ops.do_upload(client, str(tmp_path / "absent.docx"))

    def test_raw_with_to_raises(self, client, docx):
        with pytest.raises(ValueError, match="mutually exclusive"):
            ops.do_upload(client, docx, raw=True, to="doc")

    def test_unknown_to_raises(self, client, docx):
        with pytest.raises(ValueError, match="doc, sheet, or slides"):
            ops.do_upload(client, docx, to="banana")

    def test_to_disagreeing_with_the_replaced_file_raises(self, client, docx):
        client.get_file_mime.return_value = \
            "application/vnd.google-apps.spreadsheet"
        with pytest.raises(ValueError, match="spreadsheet"):
            ops.do_upload(client, docx, "SHEET1", to="doc")
        client.update_file_content.assert_not_called()

    def test_to_matching_the_replaced_file_is_fine(self, client, docx):
        self._uploaded(client, id="DOC1")
        client.get_file_mime.return_value = DOC_MIME
        assert ops.do_upload(client, docx, "DOC1", to="doc")["action"] == "replaced"

    def test_raw_source_with_no_native_equivalent_uploads_as_is(
            self, client, tmp_path):
        self._uploaded(client, mimeType="application/pdf")
        path = str(tmp_path / "scan.pdf")
        open(path, "wb").write(b"%PDF")
        ops.do_upload(client, path)
        client.upload_file.assert_called_once_with(
            path, "application/pdf", name="scan.pdf", convert_to=None,
            parent_folder_id=None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_drive_ops.py::TestDoUpload -v`
Expected: FAIL — `AttributeError: module 'drive_cli.ops' has no attribute 'do_upload'`.

- [ ] **Step 3: Write the implementation**

In `src/drive_cli/ops.py`, change the imports at the top from:

```python
from typing import Any, Dict, List, Optional

from sheet_client import SheetsClient
```

to:

```python
import os
from typing import Any, Dict, List, Optional

from sheet_client import SheetsClient

from . import mimes
```

Then append after `do_parents`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_drive_ops.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/john/src/sheet-cli
git add src/drive_cli/ops.py test/test_drive_ops.py
git commit -m "feat(drive): do_upload verb core"
```

---

### Task 4: `ops.do_export`

**Files:**
- Modify: `src/drive_cli/ops.py`
- Test: `test/test_drive_ops.py`

**Model:** `sonnet` — the 10MB error path needs the exception types wired correctly across two modules.

**Interfaces:**
- Consumes: `mimes.export_mime`, `mimes.NATIVE_EXPORTS` (Task 1); `client.get_file_mime`, `client.export_file` (Task 2); `SheetsAPIError` and `SheetsClientError` from `sheet_client.exceptions`.
- Produces: `do_export(client, file_id, out_path, *, mime=None) -> Dict[str, Any]` returning `{"id", "name", "mimeType", "exported_as", "path", "bytes"}`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_drive_ops.py`, before the `if __name__` block:

```python
# -------------------------------- do_export --------------------------------

SLIDES_MIME = "application/vnd.google-apps.presentation"


class TestDoExport:
    def _exported(self, client, name="Flyer", size=1234):
        client.export_file.return_value = {
            "id": "X", "name": name, "mimeType": "ignored", "bytes": size}

    def test_doc_to_pdf(self, client):
        client.get_file_mime.return_value = DOC_MIME
        self._exported(client)
        result = ops.do_export(client, "DOC1", "out.pdf")
        client.export_file.assert_called_once_with(
            "DOC1", "out.pdf", export_mime="application/pdf")
        assert result == {"id": "DOC1", "name": "Flyer", "mimeType": DOC_MIME,
                          "exported_as": "application/pdf", "path": "out.pdf",
                          "bytes": 1234}

    def test_doc_to_docx(self, client):
        client.get_file_mime.return_value = DOC_MIME
        self._exported(client)
        ops.do_export(client, "DOC1", "out.docx")
        assert client.export_file.call_args[1]["export_mime"] == DOCX

    def test_sheet_to_csv(self, client):
        client.get_file_mime.return_value = SHEET_MIME
        self._exported(client)
        ops.do_export(client, "SID", "out.csv")
        assert client.export_file.call_args[1]["export_mime"] == "text/csv"

    def test_slides_to_pptx(self, client):
        client.get_file_mime.return_value = SLIDES_MIME
        self._exported(client)
        ops.do_export(client, "PID", "out.pptx")
        assert client.export_file.call_args[1]["export_mime"].endswith(
            "presentationml.presentation")

    def test_mime_overrides_the_extension_guess(self, client):
        client.get_file_mime.return_value = DOC_MIME
        self._exported(client)
        result = ops.do_export(client, "DOC1", "out.bin", mime="application/pdf")
        assert client.export_file.call_args[1]["export_mime"] == "application/pdf"
        assert result["exported_as"] == "application/pdf"

    def test_non_native_file_is_a_plain_media_download(self, client):
        client.get_file_mime.return_value = "application/pdf"
        self._exported(client, name="scan.pdf", size=99)
        result = ops.do_export(client, "PDF1", "out.pdf")
        client.export_file.assert_called_once_with(
            "PDF1", "out.pdf", export_mime=None)
        assert result["exported_as"] == "application/pdf"
        assert result["bytes"] == 99

    def test_mime_on_a_non_native_file_raises(self, client):
        client.get_file_mime.return_value = "application/pdf"
        with pytest.raises(ValueError, match="needs no conversion"):
            ops.do_export(client, "PDF1", "out.pdf", mime="application/pdf")
        client.export_file.assert_not_called()

    def test_extension_invalid_for_the_type_lists_the_valid_ones(self, client):
        client.get_file_mime.return_value = SHEET_MIME
        with pytest.raises(ValueError, match="xlsx"):
            ops.do_export(client, "SID", "out.epub")
        client.export_file.assert_not_called()

    def test_export_over_the_size_limit_is_re_raised_with_the_reason(self, client):
        from sheet_client.exceptions import SheetsAPIError, SheetsClientError

        client.get_file_mime.return_value = DOC_MIME
        client.export_file.side_effect = SheetsAPIError(
            "API error 403: exportSizeLimitExceeded", status_code=403)
        with pytest.raises(SheetsClientError, match="10MB"):
            ops.do_export(client, "DOC1", "out.pdf")

    def test_other_api_errors_pass_through(self, client):
        from sheet_client.exceptions import SheetsAPIError

        client.get_file_mime.return_value = DOC_MIME
        client.export_file.side_effect = SheetsAPIError(
            "API error 404: not found", status_code=404)
        with pytest.raises(SheetsAPIError, match="404"):
            ops.do_export(client, "DOC1", "out.pdf")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_drive_ops.py::TestDoExport -v`
Expected: FAIL — `AttributeError: module 'drive_cli.ops' has no attribute 'do_export'`.

- [ ] **Step 3: Write the implementation**

In `src/drive_cli/ops.py`, extend the imports added in Task 3 with the exception types:

```python
from sheet_client import SheetsClient
from sheet_client.exceptions import SheetsAPIError, SheetsClientError
```

Add the constant next to the existing `FOLDER_MIME` / `SPREADSHEET_MIME` at the top of the module:

```python
NATIVE_PREFIX = "application/vnd.google-apps."
```

Append after `_upload_create`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_drive_ops.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/john/src/sheet-cli
git add src/drive_cli/ops.py test/test_drive_ops.py
git commit -m "feat(drive): do_export verb core"
```

---

### Task 5: CLI wiring

**Files:**
- Modify: `src/drive_cli/cli.py` (module docstring, two `cmd_*` functions, two subparsers, the `add_account` loop)
- Test: `test/test_drive_cli.py`

**Model:** `sonnet` — argparse edits in several places of one file, and the positional order differs between the two verbs.

**Interfaces:**
- Consumes: `ops.do_upload`, `ops.do_export` (Tasks 3 and 4).
- Produces: `cmd_upload(args)`, `cmd_export(args)`; the `upload` and `export` subcommands.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_drive_cli.py`:

```python
class TestUpload:
    @pytest.fixture
    def upload_client(self, fake_client):
        fake_client.upload_file.return_value = {
            "id": "NEW", "name": "flyer",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "u", "parents": []}
        fake_client.update_file_content.return_value = {
            "id": "DOC1", "name": "flyer",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "u", "parents": []}
        return fake_client

    @pytest.fixture
    def docx(self, tmp_path):
        path = tmp_path / "flyer.docx"
        path.write_bytes(b"x")
        return str(path)

    def test_upload_to_root_prints_json(self, upload_client, docx):
        out, _, code = run_cli(["upload", docx], upload_client)
        assert code in (None, 0)
        assert json.loads(out)["action"] == "created"
        assert upload_client.upload_file.call_args[1]["parent_folder_id"] is None

    def test_upload_into_a_folder(self, upload_client, docx):
        upload_client.get_file_mime.return_value = \
            "application/vnd.google-apps.folder"
        run_cli(["upload", docx, "FOLDER1"], upload_client)
        assert upload_client.upload_file.call_args[1]["parent_folder_id"] == "FOLDER1"

    def test_upload_replaces_a_file(self, upload_client, docx):
        upload_client.get_file_mime.return_value = \
            "application/vnd.google-apps.document"
        out, _, _ = run_cli(["upload", docx, "DOC1"], upload_client)
        upload_client.update_file_content.assert_called_once()
        assert json.loads(out)["action"] == "replaced"

    def test_raw_flag(self, upload_client, docx):
        run_cli(["upload", docx, "--raw"], upload_client)
        assert upload_client.upload_file.call_args[1]["convert_to"] is None

    def test_to_flag(self, upload_client, tmp_path):
        path = str(tmp_path / "notes.txt")
        open(path, "w").write("hi")
        run_cli(["upload", path, "--to", "doc"], upload_client)
        assert upload_client.upload_file.call_args[1]["convert_to"] == \
            "application/vnd.google-apps.document"

    def test_name_and_mime_flags(self, upload_client, tmp_path):
        path = str(tmp_path / "data")
        open(path, "w").write("a,b")
        run_cli(["upload", path, "--mime", "text/csv", "--name", "Q3"],
                upload_client)
        assert upload_client.upload_file.call_args[0][1] == "text/csv"
        assert upload_client.upload_file.call_args[1]["name"] == "Q3"

    def test_raw_and_to_are_mutually_exclusive(self, upload_client, docx):
        _, err, code = run_cli(["upload", docx, "--raw", "--to", "doc"],
                               upload_client)
        assert code == 2
        upload_client.upload_file.assert_not_called()

    def test_missing_file_exits_2(self, upload_client, tmp_path):
        _, err, code = run_cli(["upload", str(tmp_path / "absent.docx")],
                               upload_client)
        assert code == 2
        assert "no such file" in err


class TestExport:
    @pytest.fixture
    def export_client(self, fake_client):
        fake_client.get_file_mime.return_value = \
            "application/vnd.google-apps.document"
        fake_client.export_file.return_value = {
            "id": "DOC1", "name": "Flyer", "mimeType": "x", "bytes": 10}
        return fake_client

    def test_export_guesses_from_the_extension(self, export_client, tmp_path):
        out_path = str(tmp_path / "out.pdf")
        out, _, code = run_cli(["export", "DOC1", out_path], export_client)
        assert code in (None, 0)
        export_client.export_file.assert_called_once_with(
            "DOC1", out_path, export_mime="application/pdf")
        assert json.loads(out)["exported_as"] == "application/pdf"

    def test_export_mime_flag(self, export_client, tmp_path):
        out_path = str(tmp_path / "out.bin")
        run_cli(["export", "DOC1", out_path, "--mime", "text/plain"],
                export_client)
        assert export_client.export_file.call_args[1]["export_mime"] == "text/plain"

    def test_export_bad_extension_exits_2(self, export_client, tmp_path):
        _, err, code = run_cli(["export", "DOC1", str(tmp_path / "out.xlsx")],
                               export_client)
        assert code == 2
        assert "cannot export" in err

    def test_export_mime_on_a_non_native_file_exits_2(self, export_client, tmp_path):
        export_client.get_file_mime.return_value = "application/pdf"
        _, err, code = run_cli(
            ["export", "PDF1", str(tmp_path / "out.pdf"), "--mime", "application/pdf"],
            export_client)
        assert code == 2
        assert "needs no conversion" in err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/test_drive_cli.py::TestUpload test/test_drive_cli.py::TestExport -v`
Expected: FAIL — argparse rejects `upload` as an invalid choice, so every test exits 2 with "invalid choice".

- [ ] **Step 3: Add the command functions**

In `src/drive_cli/cli.py`, insert after `cmd_parents` (currently ending at line 82) and before `cmd_inventory`:

```python
def cmd_upload(args):
    client = _client(args)
    _print_json(ops.do_upload(client, args.file, args.id, raw=args.raw,
                              to=args.to, name=args.name, mime=args.mime))


def cmd_export(args):
    client = _client(args)
    _print_json(ops.do_export(client, args.id, args.file, mime=args.mime))
```

- [ ] **Step 4: Add the subparsers**

In `build_parser`, insert after the `p_parents` block (currently ending with `p_parents.set_defaults(func=cmd_parents)`) and before `p_inv`:

```python
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
```

Then add both to the `add_account` loop at the end of `build_parser`, changing:

```python
    for p in (p_list, p_copy, p_new, p_move, p_parents, p_inv, p_plan, p_chown,
              p_accept, p_auth):
        add_account(p)
```

to:

```python
    for p in (p_list, p_copy, p_new, p_move, p_parents, p_upload, p_export,
              p_inv, p_plan, p_chown, p_accept, p_auth):
        add_account(p)
```

- [ ] **Step 5: Update the module docstring**

In the usage block at the top of `src/drive_cli/cli.py`, add two lines after the `parents` line:

```
    drive-cli parents   ID
    drive-cli upload    FILE [ID] [--name NAME] [--raw | --to doc|sheet|slides] [--mime TYPE]
    drive-cli export    ID FILE [--mime TYPE]
    drive-cli inventory ROOT [-o MANIFEST]
```

- [ ] **Step 6: Run the whole suite**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/ -v`
Expected: all tests PASS, no regressions in `test_drive_cli.py`, `test_drive_ops.py`, `test_client.py`.

- [ ] **Step 7: Commit**

```bash
cd /home/john/src/sheet-cli
git add src/drive_cli/cli.py test/test_drive_cli.py
git commit -m "feat(drive-cli): upload and export subcommands"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md` (the `drive-cli` command table around line 219, and the examples around line 249)
- Modify: `CLAUDE.md` (the `drive-cli` command table around line 126)
- Modify: `API.md` (the Core API table around line 68, and new sections after `copy_folder()` at line 1027)

**Model:** `haiku` — prose insertions at named locations, with the text supplied below.

**Interfaces:** none — docs only.

- [ ] **Step 1: README.md command table**

In `README.md`, add two lines to the `drive-cli` usage block after the `parents` line (currently line 224):

```
drive-cli upload FILE [ID] [--raw|--to doc|sheet|slides]  put a local file into Drive
drive-cli export ID FILE [--mime TYPE]      write a Drive file out as a local file
```

- [ ] **Step 2: README.md examples**

In `README.md`, after the `drive-cli list PARENT_FOLDER` example (currently line 249), add:

````markdown

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
````

- [ ] **Step 3: CLAUDE.md command table**

In `CLAUDE.md`, add two lines to the command block after the `parents` line (currently line 131):

```
drive-cli upload  FILE [ID] [--raw|--to K]  upload a local file (ID = folder, or file to replace)
drive-cli export  ID FILE [--mime TYPE]     write a Drive file out locally
```

- [ ] **Step 4: API.md Core API table**

In `API.md`, add three rows to the Core API table after the `get_file_mime` row (currently line 71):

```
| `upload_file(path, source_mime, name, convert_to, parent_folder_id)` | Create a Drive file from local bytes, optionally converting |
| `update_file_content(file_id, path, source_mime, name)` | Replace a Drive file's bytes, keeping its ID |
| `export_file(file_id, out_path, export_mime)` | Write a Drive file to a local path (export or media download) |
```

- [ ] **Step 5: API.md method sections**

In `API.md`, insert after the `copy_folder()` section's trailing `---` (currently line 1027) and before `## create_folder()`:

````markdown
## upload_file()

Create a Drive file from local bytes. With `convert_to` set to an
`application/vnd.google-apps.*` type, Drive converts on the way in; without it
the bytes are stored as-is. The upload is resumable, so files past Drive's 5MB
simple-upload limit need no separate code path.

```python
def upload_file(path, source_mime, *, name, convert_to=None,
                parent_folder_id=None) -> dict
```

**Returns:** `{'id', 'name', 'mimeType', 'webViewLink', 'parents'}`.

---

## update_file_content()

Replace an existing Drive file's bytes. The file keeps its ID, URL, sharing and
comments, and Drive records a new revision. The stored format is fixed by the
existing file, so there is no conversion argument. `name` renames as well.

```python
def update_file_content(file_id, path, source_mime, *, name=None) -> dict
```

**Returns:** `{'id', 'name', 'mimeType', 'webViewLink', 'parents'}`.

---

## export_file()

Write a Drive file to `out_path`. With `export_mime` this is `files.export`,
converting a Google-native document to that type; without it, a plain
`files.get` media download. Downloads run through `MediaIoBaseDownload` in
chunks, so a large export never has to fit in memory at once. Drive refuses to
export a document over 10MB, which surfaces as a 403.

```python
def export_file(file_id, out_path, export_mime=None) -> dict
```

**Returns:** `{'id', 'name', 'mimeType', 'bytes'}` — `mimeType` is the Drive
file's type, not the exported one.

---
````

- [ ] **Step 6: Commit**

```bash
cd /home/john/src/sheet-cli
git add README.md CLAUDE.md API.md
git commit -m "docs: drive-cli upload and export"
```

---

### Task 7: Full-suite verification

**Files:** none.

**Model:** `haiku` — running two commands and reporting their output.

- [ ] **Step 1: Run the whole test suite**

Run: `cd /home/john/src/sheet-cli && python -m pytest test/ -v --ignore=test/test_integration.py`
Expected: PASS, zero failures.

- [ ] **Step 2: Check the CLI help renders**

Run: `cd /home/john/src/sheet-cli && python -c "import sys; sys.path.insert(0,'src'); from drive_cli.cli import build_parser; build_parser().parse_args(['upload','--help'])"`
Expected: the `upload` usage block, listing `--name`, `--raw`, `--to`, `--mime`, `--as`, then exit 0.
