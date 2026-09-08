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
