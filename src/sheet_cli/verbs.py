"""Unary verbs (get, put, del, new) for the unified CLI grammar.

Each verb dispatches on the target's TargetType. Binary verbs (copy, move)
live in dispatch.py because they coordinate two targets and pick server-side
APIs when possible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sheet_client import CellData, SheetsClient

from .grammar import (
    GrammarError,
    Target,
    TargetType,
    a1_range_for_locator,
    classify,
    is_single_cell,
    render,
)


# ----------------------------- helpers -----------------------------


def _resolve_sheet_id(client: SheetsClient, spreadsheet_id: str, sheet_title: str) -> int:
    """Resolve a sheet title to its numeric sheetId within a spreadsheet."""
    meta = client.meta_read(spreadsheet_id)
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_title:
            return int(props.get("sheetId"))
    raise GrammarError(f"sheet not found: {sheet_title!r}")


def _locator_to_dimension_range(target: Target, sheet_id: int) -> Dict[str, Any]:
    """Convert a ROW/COLUMN target into a DimensionRange for insert/delete."""
    loc = target.locator
    if loc is None:
        raise GrammarError("cannot build DimensionRange without a locator")
    tt = classify(target)
    if tt == TargetType.ROW:
        idx = int(loc) - 1
        return {
            "sheetId": sheet_id,
            "dimension": "ROWS",
            "startIndex": idx,
            "endIndex": idx + 1,
        }
    if tt == TargetType.COLUMN:
        from sheet_client.utils import column_to_index
        idx = column_to_index(loc)
        return {
            "sheetId": sheet_id,
            "dimension": "COLUMNS",
            "startIndex": idx,
            "endIndex": idx + 1,
        }
    raise GrammarError(f"expected ROW or COLUMN, got {tt.value}")


# ------------------------------ get --------------------------------


def do_get(client: SheetsClient, target: Target) -> Any:
    """Read what's at the target. Returns the raw API response.

    - DRIVE        → list of spreadsheet file metadata
    - SPREADSHEET  → full meta_read() response
    - SHEET        → values.get response for the whole sheet
    - RANGE/ROW/COL→ values.get response for the locator
    """
    if target.property is not None:
        from . import properties
        return properties.dispatch("get", client, target, None)

    tt = classify(target)

    if tt == TargetType.DRIVE:
        return client.list_spreadsheets()

    assert target.spreadsheet_id is not None

    if tt == TargetType.SPREADSHEET:
        return client.meta_read(target.spreadsheet_id)

    a1 = a1_range_for_locator(target)
    return client.read(
        target.spreadsheet_id,
        [a1],
        types=CellData.VALUE | CellData.FORMULA,
    )


# ------------------------------ put --------------------------------


def do_put(client: SheetsClient, target: Target, data: Any) -> Dict[str, Any]:
    """Write data at the target.

    ``data`` shapes accepted:
    - ``{A1: value, ...}``          — cell-keyed, values become 1x1 writes
    - ``{range: [[...]], ...}``     — range-keyed, values are 2D arrays
    - ``[[...]]``                   — bare 2D array (requires RANGE/ROW/COLUMN target)
    - scalar                        — single cell value (requires cell-shaped locator)
    """
    if target.property is not None:
        from . import properties
        return properties.dispatch("put", client, target, data)

    tt = classify(target)
    if tt in (TargetType.DRIVE, TargetType.SPREADSHEET):
        raise GrammarError(f"put is not valid for {tt.value} targets")

    assert target.spreadsheet_id is not None

    write_ops: List[Dict[str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            # key may be a locator relative to the target's sheet; if it already
            # contains '!', pass through, otherwise qualify with the target sheet.
            if "!" in key:
                range_str = key
            else:
                sub = Target(target.spreadsheet_id, target.sheet, key)
                range_str = a1_range_for_locator(sub)
            if isinstance(value, list) and value and isinstance(value[0], list):
                write_ops.append({"range": range_str, "values": value})
            else:
                write_ops.append({"range": range_str, "values": [[value]]})
    elif isinstance(data, list):
        if tt not in (TargetType.RANGE, TargetType.ROW, TargetType.COLUMN, TargetType.SHEET):
            raise GrammarError("bare 2D array requires a range/row/column/sheet target")
        values = data if data and isinstance(data[0], list) else [data]
        write_ops.append({"range": a1_range_for_locator(target), "values": values})
    else:
        # scalar — target must resolve to a single cell; otherwise the caller
        # probably expected the value to fill a range, but the API would
        # silently drop it into the top-left cell only.
        if not is_single_cell(target):
            raise GrammarError(
                "scalar put requires a single-cell target "
                f"(got {tt.value} {target.locator!r}); pass a 2D list instead"
            )
        write_ops.append({"range": a1_range_for_locator(target), "values": [[data]]})

    return client.write(target.spreadsheet_id, write_ops)


# ------------------------------ del --------------------------------


def do_del(client: SheetsClient, target: Target) -> Dict[str, Any]:
    """Delete or clear what's at the target."""
    if target.property is not None:
        from . import properties
        return properties.dispatch("del", client, target, None)

    tt = classify(target)

    if tt == TargetType.DRIVE:
        raise GrammarError("del with no target would delete everything — refuse")

    assert target.spreadsheet_id is not None

    if tt == TargetType.SPREADSHEET:
        client.delete_spreadsheet(target.spreadsheet_id)
        return {"deleted": render(target)}

    if tt == TargetType.SHEET:
        assert target.sheet is not None
        sheet_id = _resolve_sheet_id(client, target.spreadsheet_id, target.sheet)
        return client.meta_write(target.spreadsheet_id, [{
            "deleteSheet": {"sheetId": sheet_id}
        }])

    if tt == TargetType.RANGE:
        return client.clear(target.spreadsheet_id, [a1_range_for_locator(target)])

    # ROW / COLUMN — delete the dimension
    assert target.sheet is not None
    sheet_id = _resolve_sheet_id(client, target.spreadsheet_id, target.sheet)
    return client.meta_write(target.spreadsheet_id, [{
        "deleteDimension": {"range": _locator_to_dimension_range(target, sheet_id)}
    }])


# ------------------------------ new --------------------------------


def do_new(
    client: SheetsClient,
    target: Target,
    *,
    side: Optional[str] = None,
    data: Any = None,
) -> Dict[str, Any]:
    """Create what the target describes.

    - DRIVE/SPREADSHEET: `new "Title"` or `new SID` treats the SID slot as a
      title. Creates a new spreadsheet.
    - SHEET: add a sheet with the given title.
    - ROW/COLUMN: insert a dimension adjacent to the locator. `side` is one of
      above/below (rows) or left/right (columns); defaults to below/right.
    - .property: dispatches to the property handler; ``data`` carries the body
      (e.g. a ConditionalFormatRule for ``new .conditional``).
    """
    if target.property is not None:
        from . import properties
        return properties.dispatch("new", client, target, data)

    # Non-property paths don't accept a body — make it explicit instead of
    # silently discarding it.
    if data is not None:
        raise GrammarError("new on this target does not accept a stdin body")

    tt = classify(target)

    if tt in (TargetType.DRIVE, TargetType.SPREADSHEET):
        # The SID slot is interpreted as a title here. A bare `new` with no
        # positional becomes an untitled spreadsheet.
        title = target.spreadsheet_id or "Untitled spreadsheet"
        return client.create(title)

    assert target.spreadsheet_id is not None

    if tt == TargetType.SHEET:
        assert target.sheet is not None
        return client.meta_write(target.spreadsheet_id, [{
            "addSheet": {"properties": {"title": target.sheet}}
        }])

    if tt in (TargetType.ROW, TargetType.COLUMN):
        assert target.sheet is not None
        sheet_id = _resolve_sheet_id(client, target.spreadsheet_id, target.sheet)
        dim_range = _locator_to_dimension_range(target, sheet_id)

        if tt == TargetType.ROW:
            chosen = side or "below"
            if chosen not in ("above", "below"):
                raise GrammarError(f"row side must be above|below, got {chosen!r}")
            after = chosen == "below"
        else:
            chosen = side or "right"
            if chosen not in ("left", "right"):
                raise GrammarError(f"column side must be left|right, got {chosen!r}")
            after = chosen == "right"

        if after:
            dim_range["startIndex"] += 1
            dim_range["endIndex"] += 1

        return client.meta_write(target.spreadsheet_id, [{
            "insertDimension": {"range": dim_range, "inheritFromBefore": after}
        }])

    raise GrammarError(f"new is not valid for {tt.value} targets")
