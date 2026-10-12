"""Pure builders for spreadsheets.batchUpdate request bodies.

The property handlers in ``properties.py`` and the ``batch`` verb both turn a
payload into the same Google API request. Constructing them here means one
definition, so the two cannot drift.
"""

from __future__ import annotations

from typing import Any, Dict, List


def fields_path(d: Dict[str, Any], prefix: str = "") -> List[str]:
    """Walk ``d`` to its leaves and return dotted field paths.

    An empty dict terminates the walk and becomes a "replace this whole
    subtree" mask, matching Sheets API semantics for clearing.
    """
    paths: List[str] = []
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            paths.extend(fields_path(v, prefix=f"{path}."))
        else:
            paths.append(path)
    return paths


def fields_mask(d: Dict[str, Any], prefix: str = "") -> str:
    """Join leaf paths into a comma-separated field mask."""
    return ",".join(fields_path(d, prefix=prefix))


def format_request(grid_range: Dict[str, Any], fmt: Dict[str, Any]) -> Dict[str, Any]:
    return {"repeatCell": {
        "range": grid_range,
        "cell": {"userEnteredFormat": fmt},
        "fields": fields_mask(fmt, prefix="userEnteredFormat."),
    }}


def note_request(grid_range: Dict[str, Any], text: str) -> Dict[str, Any]:
    return {"repeatCell": {
        "range": grid_range,
        "cell": {"note": text},
        "fields": "note",
    }}


def borders_request(grid_range: Dict[str, Any], borders: Dict[str, Any]) -> Dict[str, Any]:
    return {"updateBorders": {"range": grid_range, **borders}}


def validation_request(grid_range: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    return {"setDataValidation": {"range": grid_range, "rule": rule}}


def merge_request(grid_range: Dict[str, Any], merge_type: str) -> Dict[str, Any]:
    return {"mergeCells": {"range": grid_range, "mergeType": merge_type}}


def dimension_request(dimension_range: Dict[str, Any], pixels: int) -> Dict[str, Any]:
    return {"updateDimensionProperties": {
        "range": dimension_range,
        "properties": {"pixelSize": int(pixels)},
        "fields": "pixelSize",
    }}
