"""Property handlers for target.property dispatch.

Every non-value write to a spreadsheet (formatting, borders, freeze, named
ranges, conditional rules, etc.) is a property of a resource. A property is
addressed as ``TARGET.name`` or ``TARGET.name.key`` / ``TARGET.name[key]``
for collection elements.

Handlers register for a (property-name, resource-scope) pair and expose any
subset of {get, put, del, new}. The ``dispatch`` entry point routes verbs
(``do_*`` in verbs.py) through the registry when ``target.property`` is set.

Add a new property type by writing one tiny handler set and calling
``register(...)`` once — no changes elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from sheet_client import CellData, SheetsClient
from sheet_client.utils import a1_to_grid_range, column_to_index

from .grammar import (
    GrammarError,
    Target,
    TargetType,
    a1_range_for_locator,
    classify,
)


# ----------------------------- registry -----------------------------


Handler = Callable[[SheetsClient, Target, Optional[Any]], Any]


@dataclass
class PropertyHandler:
    get: Optional[Handler] = None
    put: Optional[Handler] = None
    del_: Optional[Handler] = None
    new: Optional[Handler] = None


_REGISTRY: Dict[Tuple[str, TargetType], PropertyHandler] = {}


def register(
    name: str,
    scope: TargetType,
    *,
    get: Optional[Handler] = None,
    put: Optional[Handler] = None,
    del_: Optional[Handler] = None,
    new: Optional[Handler] = None,
) -> None:
    _REGISTRY[(name, scope)] = PropertyHandler(get=get, put=put, del_=del_, new=new)


def dispatch(verb: str, client: SheetsClient, target: Target, data: Any = None) -> Any:
    """Invoke a property handler for ``verb`` on ``target``.

    Raises GrammarError if no handler is registered for (property, scope) or
    if the handler doesn't support this verb.
    """
    prop = target.property
    if prop is None:
        raise GrammarError("dispatch called without a property")
    scope = classify(target)
    handler = _REGISTRY.get((prop.name, scope))
    if handler is None:
        raise GrammarError(
            f"property {prop.name!r} is not valid for {scope.value} targets"
        )
    fn = getattr(handler, verb if verb != "del" else "del_")
    if fn is None:
        raise GrammarError(
            f"{verb} is not supported on property {prop.name!r} "
            f"for {scope.value} targets"
        )
    return fn(client, target, data)


# ----------------------------- helpers -----------------------------


def _sheet_props(client: SheetsClient, spreadsheet_id: str, title: str) -> Dict[str, Any]:
    """Return the sheet's properties dict (raising if not found)."""
    meta = client.meta_read(spreadsheet_id)
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == title:
            return props
    raise GrammarError(f"sheet not found: {title!r}")


def _sheet_id(client: SheetsClient, target: Target) -> int:
    if target.sheet is None:
        raise GrammarError("sheet target required")
    assert target.spreadsheet_id is not None
    return int(_sheet_props(client, target.spreadsheet_id, target.sheet)["sheetId"])


def _grid_range(client: SheetsClient, target: Target) -> Dict[str, Any]:
    if target.locator is None:
        raise GrammarError("range target required")
    sid = _sheet_id(client, target)
    return a1_to_grid_range(target.locator, sheet_id=sid)


def _dimension_range(
    client: SheetsClient, target: Target, dimension: str
) -> Dict[str, Any]:
    """Build a DimensionRange for a row or column target."""
    if target.locator is None:
        raise GrammarError("dimension target required")
    sid = _sheet_id(client, target)
    if dimension == "ROWS":
        idx = int(target.locator) - 1
    else:
        idx = column_to_index(target.locator)
    return {
        "sheetId": sid,
        "dimension": dimension,
        "startIndex": idx,
        "endIndex": idx + 1,
    }


def _read_target_sheet_grid(
    client: SheetsClient, target: Target
) -> Dict[str, Any]:
    """Fetch grid data for target and return the sheet block matching target.sheet.

    ``spreadsheets.get(includeGridData=True, ranges=[...])`` returns *every*
    sheet in the spreadsheet; only the sheet(s) intersecting ``ranges`` have
    their ``data`` field populated. We pick out the one whose title matches
    ``target.sheet`` — blindly taking ``sheets[0]`` would return data from the
    wrong sheet whenever the target isn't the first tab.
    """
    sid = target.spreadsheet_id
    assert sid is not None
    # Sheets API values.get accepts A1 ranges, not bare dimension locators:
    # "Sheet1!C" happens to work (interpreted as the whole column) but
    # "Sheet1!3" is rejected. Expand bare row/column locators to "N:N"
    # form so the API is happy. This mirrors what users would write by hand.
    t_type = classify(target)
    if t_type in (TargetType.ROW, TargetType.COLUMN) and ":" not in (target.locator or ""):
        target = replace(target, locator=f"{target.locator}:{target.locator}")
    a1 = a1_range_for_locator(target)
    response = client.read(
        sid,
        [a1],
        types=CellData.VALUE | CellData.FORMAT | CellData.NOTE,
    )
    sheets = response.get("sheets", [])
    if target.sheet is None:
        # No sheet specified — the API uses the first tab; mirror that.
        return sheets[0] if sheets else {}
    for s in sheets:
        if s.get("properties", {}).get("title") == target.sheet:
            return s
    raise GrammarError(f"sheet {target.sheet!r} not found in grid response")


def _cells_from_sheet_block(sheet_block: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    """Extract the 2D cell matrix from a single sheet block of a grid-data payload."""
    data_blocks = sheet_block.get("data", [])
    if not data_blocks:
        return []
    row_data = data_blocks[0].get("rowData", [])
    return [rd.get("values", []) for rd in row_data]


# ----------- fields helper (for repeatCell / updateSheetProperties) ---------


def _fields_path(d: Dict[str, Any], prefix: str = "") -> List[str]:
    """Walk ``d`` to leaves and return dotted field paths.

    ``{"textFormat": {"bold": True}, "backgroundColor": {"red": 1.0}}`` →
    ``["userEnteredFormat.textFormat.bold", "userEnteredFormat.backgroundColor.red"]``
    when called with ``prefix="userEnteredFormat."``. A non-dict leaf (including
    an empty dict) terminates the walk — an empty dict becomes a "replace this
    whole subtree" field mask, matching Sheets API semantics for clearing.
    """
    paths: List[str] = []
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            paths.extend(_fields_path(v, prefix=f"{path}."))
        else:
            paths.append(path)
    return paths


def _fields_mask(d: Dict[str, Any], prefix: str = "") -> str:
    """Join the leaf paths into a comma-separated fields mask."""
    return ",".join(_fields_path(d, prefix=prefix))


# ----------- color parsing -----------


def _parse_color(value: Any) -> Dict[str, float]:
    """Accept '#rrggbb', '#rrggbbaa', or a dict with red/green/blue/alpha.

    Dict values must already be floats in ``[0, 1]`` (Sheets API convention).
    Out-of-range values are rejected so we catch the common ``{"red": 255}``
    mistake client-side rather than surfacing a 400 from the server.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k not in ("red", "green", "blue", "alpha"):
                continue
            fv = float(v)
            if not 0.0 <= fv <= 1.0:
                raise GrammarError(
                    f"color channel {k!r}={v!r} must be in [0, 1] (not 0-255)"
                )
            out[k] = fv
        return out
    if not isinstance(value, str):
        raise GrammarError(f"color must be '#rrggbb' or dict, got {type(value).__name__}")
    s = value.strip().lstrip("#")
    if len(s) not in (6, 8):
        raise GrammarError(f"color {value!r} must be 6 or 8 hex digits")
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError:
        raise GrammarError(f"invalid hex color: {value!r}")
    out = {"red": r, "green": g, "blue": b}
    if len(s) == 8:
        out["alpha"] = int(s[6:8], 16) / 255.0
    return out


def _render_color(c: Dict[str, float]) -> str:
    r = int(round(c.get("red", 0.0) * 255))
    g = int(round(c.get("green", 0.0) * 255))
    b = int(round(c.get("blue", 0.0) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"


# ==========================================================================
# range properties
# ==========================================================================


def _format_get(client, target, _data):
    """Return per-cell userEnteredFormat as a 2D list (empty dict where unset)."""
    block = _read_target_sheet_grid(client, target)
    cells = _cells_from_sheet_block(block)
    return [[c.get("userEnteredFormat", {}) for c in row] for row in cells]


def _format_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError("put .format requires a JSON object of format fields")
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "repeatCell": {
            "range": gr,
            "cell": {"userEnteredFormat": data},
            "fields": _fields_mask(data, prefix="userEnteredFormat."),
        }
    }])


def _format_del(client, target, _data):
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "repeatCell": {
            "range": gr,
            "cell": {},
            "fields": "userEnteredFormat",
        }
    }])


register("format", TargetType.RANGE, get=_format_get, put=_format_put, del_=_format_del)


def _borders_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError(
            "put .borders requires a JSON object with top/bottom/left/right/"
            "innerHorizontal/innerVertical keys"
        )
    gr = _grid_range(client, target)
    body = {"range": gr, **data}
    return client.meta_write(target.spreadsheet_id, [{"updateBorders": body}])


def _borders_del(client, target, _data):
    gr = _grid_range(client, target)
    none = {"style": "NONE"}
    return client.meta_write(target.spreadsheet_id, [{
        "updateBorders": {
            "range": gr,
            "top": none, "bottom": none, "left": none, "right": none,
            "innerHorizontal": none, "innerVertical": none,
        }
    }])


def _borders_get(client, target, _data):
    block = _read_target_sheet_grid(client, target)
    cells = _cells_from_sheet_block(block)
    return [
        [
            {
                side: c.get("userEnteredFormat", {}).get("borders", {}).get(side)
                for side in ("top", "bottom", "left", "right")
                if c.get("userEnteredFormat", {}).get("borders", {}).get(side) is not None
            }
            for c in row
        ]
        for row in cells
    ]


register("borders", TargetType.RANGE, get=_borders_get, put=_borders_put, del_=_borders_del)


def _merge_get(client, target, _data):
    """List merges intersecting the target range.

    Reads via the grid-data endpoint because the ``merges`` field on a Sheet
    is only reliably populated when ``includeGridData=True``.
    """
    block = _read_target_sheet_grid(client, target)
    target_gr = _grid_range(client, target)
    return [m for m in block.get("merges", []) or [] if _ranges_overlap(m, target_gr)]


def _ranges_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    def span(r, lo, hi, default_lo=0, default_hi=10_000_000):
        return (r.get(lo, default_lo), r.get(hi, default_hi))
    ar_lo, ar_hi = span(a, "startRowIndex", "endRowIndex")
    br_lo, br_hi = span(b, "startRowIndex", "endRowIndex")
    ac_lo, ac_hi = span(a, "startColumnIndex", "endColumnIndex")
    bc_lo, bc_hi = span(b, "startColumnIndex", "endColumnIndex")
    return ar_lo < br_hi and br_lo < ar_hi and ac_lo < bc_hi and bc_lo < ac_hi


def _merge_new(client, target, data):
    gr = _grid_range(client, target)
    merge_type = (data or "MERGE_ALL") if isinstance(data, str) else "MERGE_ALL"
    return client.meta_write(target.spreadsheet_id, [{
        "mergeCells": {"range": gr, "mergeType": merge_type}
    }])


def _merge_del(client, target, _data):
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "unmergeCells": {"range": gr}
    }])


register(
    "merge", TargetType.RANGE,
    get=_merge_get, new=_merge_new, put=_merge_new, del_=_merge_del,
)


def _note_get(client, target, _data):
    block = _read_target_sheet_grid(client, target)
    cells = _cells_from_sheet_block(block)
    return [[c.get("note", "") for c in row] for row in cells]


def _note_put(client, target, data):
    text = data if isinstance(data, str) else str(data)
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "repeatCell": {
            "range": gr,
            "cell": {"note": text},
            "fields": "note",
        }
    }])


def _note_del(client, target, _data):
    return _note_put(client, target, "")


register("note", TargetType.RANGE, get=_note_get, put=_note_put, del_=_note_del)


def _validation_get(client, target, _data):
    block = _read_target_sheet_grid(client, target)
    cells = _cells_from_sheet_block(block)
    return [[c.get("dataValidation") for c in row] for row in cells]


def _validation_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError("put .validation requires a JSON object (DataValidationRule)")
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "setDataValidation": {"range": gr, "rule": data}
    }])


def _validation_del(client, target, _data):
    gr = _grid_range(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "setDataValidation": {"range": gr}
    }])


register(
    "validation", TargetType.RANGE,
    get=_validation_get, put=_validation_put, del_=_validation_del,
)


def _protected_range_put(client, target, data):
    gr = _grid_range(client, target)
    spec = data if isinstance(data, dict) else {}
    spec = {**spec, "range": gr}
    return client.meta_write(target.spreadsheet_id, [{
        "addProtectedRange": {"protectedRange": spec}
    }])


def _protected_range_get(client, target, _data):
    """List protected ranges whose GridRange overlaps the target."""
    assert target.spreadsheet_id is not None
    meta = client.meta_read(target.spreadsheet_id)
    gr = _grid_range(client, target)
    sid = gr["sheetId"]
    out = []
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") != sid:
            continue
        for p in sheet.get("protectedRanges", []) or []:
            if "range" in p and _ranges_overlap(p["range"], gr):
                out.append(p)
    return out


def _protected_range_del(client, target, _data):
    """Delete every protected range that overlaps the target."""
    existing = _protected_range_get(client, target, None)
    if not existing:
        return {"replies": []}
    requests = [
        {"deleteProtectedRange": {"protectedRangeId": p["protectedRangeId"]}}
        for p in existing
        if "protectedRangeId" in p
    ]
    if not requests:
        return {"replies": []}
    return client.meta_write(target.spreadsheet_id, requests)


register(
    "protected", TargetType.RANGE,
    get=_protected_range_get, put=_protected_range_put, new=_protected_range_put,
    del_=_protected_range_del,
)


def _is_whole_sheet_range(r: Dict[str, Any]) -> bool:
    """A ProtectedRange covers the whole sheet iff its GridRange has no bounds.

    The Sheets API's ``range: {sheetId}`` (no startRow/endRow/startColumn/
    endColumn) is the shape behind the UI's "protect sheet — except these
    cells" option. ``unprotectedRanges`` on the same ProtectedRange punches
    the holes.
    """
    return not any(
        k in r for k in ("startRowIndex", "endRowIndex", "startColumnIndex", "endColumnIndex")
    )


def _protected_sheet_list(client, target) -> List[Dict[str, Any]]:
    """Return whole-sheet protections on the target sheet."""
    assert target.spreadsheet_id is not None
    sid = _sheet_id(client, target)
    meta = client.meta_read(target.spreadsheet_id)
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") != sid:
            continue
        return [
            p for p in sheet.get("protectedRanges", []) or []
            if _is_whole_sheet_range(p.get("range", {}))
        ]
    return []


def _protected_sheet_get(client, target, _data):
    return _protected_sheet_list(client, target)


def _protected_sheet_put(client, target, data):
    """Add a whole-sheet protection, optionally with cell exceptions.

    Body JSON (``unprotectedRanges``, ``editors``, ``description``,
    ``warningOnly``, ``requestingUserCanEdit``) passes through verbatim;
    ``range`` is always overwritten to the whole-sheet form.
    """
    sid = _sheet_id(client, target)
    spec = data if isinstance(data, dict) else {}
    spec = {**spec, "range": {"sheetId": sid}}
    return client.meta_write(target.spreadsheet_id, [{
        "addProtectedRange": {"protectedRange": spec}
    }])


def _protected_sheet_del(client, target, _data):
    """Delete whole-sheet protections; narrower range protections are untouched."""
    existing = _protected_sheet_list(client, target)
    requests = [
        {"deleteProtectedRange": {"protectedRangeId": p["protectedRangeId"]}}
        for p in existing
        if "protectedRangeId" in p
    ]
    if not requests:
        return {"replies": []}
    return client.meta_write(target.spreadsheet_id, requests)


register(
    "protected", TargetType.SHEET,
    get=_protected_sheet_get, put=_protected_sheet_put, new=_protected_sheet_put,
    del_=_protected_sheet_del,
)


# ==========================================================================
# sheet properties
# ==========================================================================


def _freeze_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    grid = props.get("gridProperties", {})
    return {
        "rows": grid.get("frozenRowCount", 0),
        "columns": grid.get("frozenColumnCount", 0),
    }


def _freeze_parse(data: Any) -> Tuple[int, int]:
    if isinstance(data, int):
        return data, 0
    if isinstance(data, dict):
        return int(data.get("rows", 0)), int(data.get("columns", 0))
    if isinstance(data, str):
        parts = data.split()
        if len(parts) == 1:
            return int(parts[0]), 0
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
        raise GrammarError("freeze expects 'rows' or 'rows cols'")
    raise GrammarError(f"cannot interpret freeze value: {data!r}")


def _freeze_put(client, target, data):
    rows, cols = _freeze_parse(data)
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {
                "sheetId": sid,
                "gridProperties": {
                    "frozenRowCount": rows,
                    "frozenColumnCount": cols,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }])


def _freeze_del(client, target, _data):
    return _freeze_put(client, target, {"rows": 0, "columns": 0})


register("freeze", TargetType.SHEET, get=_freeze_get, put=_freeze_put, del_=_freeze_del)


def _color_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    c = props.get("tabColor")
    return _render_color(c) if c else None


def _color_put(client, target, data):
    color = _parse_color(data)
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {"sheetId": sid, "tabColor": color},
            "fields": "tabColor",
        }
    }])


def _color_del(client, target, _data):
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {"sheetId": sid, "tabColor": {}},
            "fields": "tabColor",
        }
    }])


register("color", TargetType.SHEET, get=_color_get, put=_color_put, del_=_color_del)


def _bool(data: Any) -> bool:
    if isinstance(data, bool):
        return data
    if isinstance(data, (int, float)):
        return bool(data)
    if isinstance(data, str):
        v = data.strip().lower()
        if v in ("true", "yes", "1", "on"):
            return True
        if v in ("false", "no", "0", "off", ""):
            return False
    raise GrammarError(f"expected boolean, got {data!r}")


def _hidden_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    return bool(props.get("hidden", False))


def _hidden_put(client, target, data):
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {"sheetId": sid, "hidden": _bool(data)},
            "fields": "hidden",
        }
    }])


def _hidden_del(client, target, _data):
    return _hidden_put(client, target, False)


register("hidden", TargetType.SHEET, get=_hidden_get, put=_hidden_put, del_=_hidden_del)


def _sheet_title_get(client, target, _data):
    # Read from the server, not target.sheet — the latter is only the lookup
    # key and would hide out-of-band renames.
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    return props.get("title")


def _sheet_title_put(client, target, data):
    if not isinstance(data, str) or not data:
        raise GrammarError("put .title requires a non-empty string")
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {"sheetId": sid, "title": data},
            "fields": "title",
        }
    }])


register("title", TargetType.SHEET, get=_sheet_title_get, put=_sheet_title_put)


# --- sheet scalar properties (hideGridlines, index, rightToLeft, row/columnCount) -----


def _update_sheet_props(client, target, properties: Dict[str, Any], fields: str) -> Any:
    """Emit a single updateSheetProperties request with ``sheetId`` filled in."""
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "updateSheetProperties": {
            "properties": {"sheetId": sid, **properties},
            "fields": fields,
        }
    }])


def _hideGridlines_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    return bool(props.get("gridProperties", {}).get("hideGridlines", False))


def _hideGridlines_put(client, target, data):
    return _update_sheet_props(
        client, target,
        {"gridProperties": {"hideGridlines": _bool(data)}},
        "gridProperties.hideGridlines",
    )


def _hideGridlines_del(client, target, _data):
    return _hideGridlines_put(client, target, False)


register(
    "hideGridlines", TargetType.SHEET,
    get=_hideGridlines_get, put=_hideGridlines_put, del_=_hideGridlines_del,
)


def _sheet_index_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    return int(props.get("index", 0))


def _sheet_index_put(client, target, data):
    return _update_sheet_props(client, target, {"index": int(data)}, "index")


register("index", TargetType.SHEET, get=_sheet_index_get, put=_sheet_index_put)


def _rtl_get(client, target, _data):
    props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
    return bool(props.get("rightToLeft", False))


def _rtl_put(client, target, data):
    return _update_sheet_props(client, target, {"rightToLeft": _bool(data)}, "rightToLeft")


def _rtl_del(client, target, _data):
    return _rtl_put(client, target, False)


register("rightToLeft", TargetType.SHEET, get=_rtl_get, put=_rtl_put, del_=_rtl_del)


def _grid_count_get(field: str) -> Handler:
    def _get(client, target, _data):
        props = _sheet_props(client, target.spreadsheet_id, target.sheet)  # type: ignore[arg-type]
        return props.get("gridProperties", {}).get(field)
    return _get


def _grid_count_put(field: str) -> Handler:
    def _put(client, target, data):
        return _update_sheet_props(
            client, target,
            {"gridProperties": {field: int(data)}},
            f"gridProperties.{field}",
        )
    return _put


register(
    "rowCount", TargetType.SHEET,
    get=_grid_count_get("rowCount"), put=_grid_count_put("rowCount"),
)
register(
    "columnCount", TargetType.SHEET,
    get=_grid_count_get("columnCount"), put=_grid_count_put("columnCount"),
)


# --- sheet.filter (basic filter, singleton per sheet) --------------------


def _sheet_filter_get(client, target, _data):
    assert target.spreadsheet_id is not None
    sid = _sheet_id(client, target)
    meta = client.meta_read(target.spreadsheet_id)
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == sid:
            return sheet.get("basicFilter")
    return None


def _sheet_filter_put(client, target, data):
    """Set the basic filter. Body is a BasicFilter; ``range`` defaults to whole sheet."""
    if data is not None and not isinstance(data, dict):
        raise GrammarError("put .filter requires a JSON object (BasicFilter) or no body")
    sid = _sheet_id(client, target)
    spec = dict(data) if isinstance(data, dict) else {}
    if "range" not in spec:
        spec["range"] = {"sheetId": sid}
    return client.meta_write(target.spreadsheet_id, [{
        "setBasicFilter": {"filter": spec}
    }])


def _sheet_filter_del(client, target, _data):
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "clearBasicFilter": {"sheetId": sid}
    }])


register(
    "filter", TargetType.SHEET,
    get=_sheet_filter_get, put=_sheet_filter_put, del_=_sheet_filter_del,
)


# --- sheet.conditional[i] -------------------------------------------------


def _conditional_rules(client, target) -> List[Dict[str, Any]]:
    assert target.spreadsheet_id is not None
    meta = client.meta_read(target.spreadsheet_id)
    sid = _sheet_id(client, target)
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == sid:
            return list(sheet.get("conditionalFormats", []) or [])
    return []


def _conditional_get(client, target, _data):
    rules = _conditional_rules(client, target)
    key = target.property.key if target.property else None
    if key is None:
        return rules
    idx = _parse_index(key, len(rules))
    return rules[idx]


def _parse_index(key: str, length: int) -> int:
    try:
        idx = int(key)
    except ValueError:
        raise GrammarError(f"index key must be an integer, got {key!r}")
    if idx < 0:
        idx += length
    if not 0 <= idx < length:
        raise GrammarError(f"conditional index {key!r} out of range [0, {length})")
    return idx


def _conditional_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError("put .conditional requires a JSON ConditionalFormatRule")
    sid = _sheet_id(client, target)
    key = target.property.key if target.property else None

    if key is None:
        # Append.
        return client.meta_write(target.spreadsheet_id, [{
            "addConditionalFormatRule": {
                "rule": {**data, "ranges": data.get("ranges") or [{"sheetId": sid}]},
                "index": len(_conditional_rules(client, target)),
            }
        }])

    rules = _conditional_rules(client, target)
    # updateConditionalFormatRule requires the index to reference an
    # existing rule — appending is only valid when no key is provided.
    idx = _parse_index(key, len(rules))
    return client.meta_write(target.spreadsheet_id, [{
        "updateConditionalFormatRule": {
            "rule": data,
            "index": idx,
            "sheetId": sid,
        }
    }])


def _conditional_new(client, target, data):
    # Force append semantics, ignoring any key.
    if not isinstance(data, dict):
        raise GrammarError("new .conditional requires a JSON ConditionalFormatRule")
    sid = _sheet_id(client, target)
    return client.meta_write(target.spreadsheet_id, [{
        "addConditionalFormatRule": {
            "rule": {**data, "ranges": data.get("ranges") or [{"sheetId": sid}]},
            "index": len(_conditional_rules(client, target)),
        }
    }])


def _conditional_del(client, target, _data):
    sid = _sheet_id(client, target)
    key = target.property.key if target.property else None
    rules = _conditional_rules(client, target)
    if key is None:
        # Delete all rules, high-index first (indices shift after each delete).
        requests = [
            {"deleteConditionalFormatRule": {"sheetId": sid, "index": i}}
            for i in range(len(rules) - 1, -1, -1)
        ]
        if not requests:
            return {"replies": []}
        return client.meta_write(target.spreadsheet_id, requests)
    idx = _parse_index(key, len(rules))
    return client.meta_write(target.spreadsheet_id, [{
        "deleteConditionalFormatRule": {"sheetId": sid, "index": idx}
    }])


register(
    "conditional", TargetType.SHEET,
    get=_conditional_get, put=_conditional_put, new=_conditional_new, del_=_conditional_del,
)


# ==========================================================================
# dimension properties
# ==========================================================================


def _dim_size_get(dimension: str) -> Handler:
    def _get(client, target, _data):
        # rowMetadata / columnMetadata are only returned with grid data, which
        # ``meta_read`` doesn't request. Use the grid-data read and read the
        # pixelSize off the ``data`` block we get back for the target range.
        block = _read_target_sheet_grid(client, target)
        data = block.get("data", [])
        if not data:
            return None
        key = "rowMetadata" if dimension == "ROWS" else "columnMetadata"
        md = data[0].get(key, [])
        return md[0].get("pixelSize") if md else None
    return _get


def _dim_size_put(dimension: str) -> Handler:
    def _put(client, target, data):
        pixels = int(data)
        dr = _dimension_range(client, target, dimension)
        return client.meta_write(target.spreadsheet_id, [{
            "updateDimensionProperties": {
                "range": dr,
                "properties": {"pixelSize": pixels},
                "fields": "pixelSize",
            }
        }])
    return _put


register("height", TargetType.ROW, get=_dim_size_get("ROWS"), put=_dim_size_put("ROWS"))
register("width", TargetType.COLUMN, get=_dim_size_get("COLUMNS"), put=_dim_size_put("COLUMNS"))


def _dim_hidden_get(dimension: str) -> Handler:
    def _get(client, target, _data):
        block = _read_target_sheet_grid(client, target)
        data = block.get("data", [])
        if not data:
            return False
        key = "rowMetadata" if dimension == "ROWS" else "columnMetadata"
        md = data[0].get(key, [])
        return bool(md[0].get("hiddenByUser", False)) if md else False
    return _get


def _dim_hidden_put(dimension: str) -> Handler:
    def _put(client, target, data):
        dr = _dimension_range(client, target, dimension)
        return client.meta_write(target.spreadsheet_id, [{
            "updateDimensionProperties": {
                "range": dr,
                "properties": {"hiddenByUser": _bool(data)},
                "fields": "hiddenByUser",
            }
        }])
    return _put


def _dim_hidden_del(dimension: str) -> Handler:
    put = _dim_hidden_put(dimension)
    def _del(client, target, _data):
        return put(client, target, False)
    return _del


register(
    "hidden", TargetType.ROW,
    get=_dim_hidden_get("ROWS"), put=_dim_hidden_put("ROWS"), del_=_dim_hidden_del("ROWS"),
)
register(
    "hidden", TargetType.COLUMN,
    get=_dim_hidden_get("COLUMNS"), put=_dim_hidden_put("COLUMNS"), del_=_dim_hidden_del("COLUMNS"),
)


def _autofit_put(dimension: str) -> Handler:
    """Trigger autoResizeDimensions for the target dimension.

    This is imperative (an action, not a state), but ``put`` is the closest
    verb fit — "put the dimension into auto-sized state". The body is ignored.
    """
    def _put(client, target, _data):
        dr = _dimension_range(client, target, dimension)
        return client.meta_write(target.spreadsheet_id, [{
            "autoResizeDimensions": {"dimensions": dr}
        }])
    return _put


register("autofit", TargetType.ROW, put=_autofit_put("ROWS"))
register("autofit", TargetType.COLUMN, put=_autofit_put("COLUMNS"))


# ==========================================================================
# spreadsheet properties
# ==========================================================================


def _spreadsheet_title_get(client, target, _data):
    meta = client.meta_read(target.spreadsheet_id)
    return meta.get("properties", {}).get("title")


def _spreadsheet_title_put(client, target, data):
    if not isinstance(data, str) or not data:
        raise GrammarError("put .title requires a non-empty string")
    return client.meta_write(target.spreadsheet_id, [{
        "updateSpreadsheetProperties": {
            "properties": {"title": data},
            "fields": "title",
        }
    }])


register("title", TargetType.SPREADSHEET, get=_spreadsheet_title_get, put=_spreadsheet_title_put)


# --- spreadsheet scalar properties (locale, timeZone, autoRecalc, …) -----


def _ss_prop_get(field: str) -> Handler:
    def _get(client, target, _data):
        return client.meta_read(target.spreadsheet_id).get("properties", {}).get(field)
    return _get


def _ss_prop_put(field: str, coerce: Callable[[Any], Any]) -> Handler:
    def _put(client, target, data):
        return client.meta_write(target.spreadsheet_id, [{
            "updateSpreadsheetProperties": {
                "properties": {field: coerce(data)},
                "fields": field,
            }
        }])
    return _put


def _require_nonempty_string(v: Any) -> str:
    if not isinstance(v, str) or not v:
        raise GrammarError("expected a non-empty string")
    return v


_AUTO_RECALC = ("ON_CHANGE", "MINUTE", "HOUR")


def _coerce_autorecalc(v: Any) -> str:
    s = _require_nonempty_string(v).upper()
    if s not in _AUTO_RECALC:
        raise GrammarError(f"autoRecalc must be one of {list(_AUTO_RECALC)}, got {v!r}")
    return s


def _require_dict(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        raise GrammarError("expected a JSON object")
    return v


register(
    "locale", TargetType.SPREADSHEET,
    get=_ss_prop_get("locale"), put=_ss_prop_put("locale", _require_nonempty_string),
)
register(
    "timeZone", TargetType.SPREADSHEET,
    get=_ss_prop_get("timeZone"), put=_ss_prop_put("timeZone", _require_nonempty_string),
)
register(
    "autoRecalc", TargetType.SPREADSHEET,
    get=_ss_prop_get("autoRecalc"), put=_ss_prop_put("autoRecalc", _coerce_autorecalc),
)
register(
    "theme", TargetType.SPREADSHEET,
    get=_ss_prop_get("spreadsheetTheme"),
    put=_ss_prop_put("spreadsheetTheme", _require_dict),
)
register(
    "defaultFormat", TargetType.SPREADSHEET,
    get=_ss_prop_get("defaultFormat"),
    put=_ss_prop_put("defaultFormat", _require_dict),
)
register(
    "iterativeCalc", TargetType.SPREADSHEET,
    get=_ss_prop_get("iterativeCalculationSettings"),
    put=_ss_prop_put("iterativeCalculationSettings", _require_dict),
)


# --- spreadsheet.named (collection keyed by name) -------------------------


def _named_ranges(client, sid: str) -> List[Dict[str, Any]]:
    return list(client.meta_read(sid).get("namedRanges", []) or [])


def _find_named(client, sid: str, name: str) -> Optional[Dict[str, Any]]:
    for nr in _named_ranges(client, sid):
        if nr.get("name") == name:
            return nr
    return None


def _named_get(client, target, _data):
    assert target.spreadsheet_id is not None
    key = target.property.key if target.property else None
    if key is None:
        return _named_ranges(client, target.spreadsheet_id)
    nr = _find_named(client, target.spreadsheet_id, key)
    if nr is None:
        raise GrammarError(f"named range not found: {key!r}")
    return nr


def _range_spec_to_grid(client, sid: str, spec: Any) -> Dict[str, Any]:
    """Accept an A1 string like 'Sheet1!A:A' or an already-formed GridRange.

    Sheet names may be single-quoted (``'My Sheet'``) and embedded quotes
    are doubled (``'Bob''s'``) — matching Sheets API and grammar.render
    conventions. The first *unquoted* ``!`` separates sheet from locator.
    """
    if isinstance(spec, dict):
        return spec
    if not isinstance(spec, str):
        raise GrammarError(
            "named range value must be an A1 string or a GridRange dict"
        )
    # Find the first unquoted '!' (locators never contain one).
    in_quote = False
    bang = -1
    for i, ch in enumerate(spec):
        if ch == "'":
            in_quote = not in_quote
        elif ch == '!' and not in_quote:
            bang = i
            break
    if bang < 0:
        raise GrammarError(f"named range value must include sheet: {spec!r}")
    sheet_name = spec[:bang]
    a1 = spec[bang + 1:]
    if len(sheet_name) >= 2 and sheet_name.startswith("'") and sheet_name.endswith("'"):
        sheet_name = sheet_name[1:-1].replace("''", "'")
    for sheet in client.meta_read(sid).get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_name:
            return a1_to_grid_range(a1, sheet_id=int(props["sheetId"]))
    raise GrammarError(f"sheet not found in named range spec: {sheet_name!r}")


def _named_put(client, target, data):
    assert target.spreadsheet_id is not None
    if target.property is None or target.property.key is None:
        raise GrammarError("put .named requires a name: SID.named.NAME VALUE")
    name = target.property.key
    gr = _range_spec_to_grid(client, target.spreadsheet_id, data)
    existing = _find_named(client, target.spreadsheet_id, name)
    if existing is None:
        return client.meta_write(target.spreadsheet_id, [{
            "addNamedRange": {"namedRange": {"name": name, "range": gr}}
        }])
    return client.meta_write(target.spreadsheet_id, [{
        "updateNamedRange": {
            "namedRange": {
                "namedRangeId": existing["namedRangeId"],
                "name": name,
                "range": gr,
            },
            "fields": "name,range",
        }
    }])


def _named_del(client, target, _data):
    assert target.spreadsheet_id is not None
    if target.property is None or target.property.key is None:
        raise GrammarError("del .named requires a name: SID.named.NAME")
    nr = _find_named(client, target.spreadsheet_id, target.property.key)
    if nr is None:
        raise GrammarError(f"named range not found: {target.property.key!r}")
    return client.meta_write(target.spreadsheet_id, [{
        "deleteNamedRange": {"namedRangeId": nr["namedRangeId"]}
    }])


register(
    "named", TargetType.SPREADSHEET,
    get=_named_get, put=_named_put, new=_named_put, del_=_named_del,
)


# --- spreadsheet.parents (Drive folder membership) -----------------------
# The only property that crosses from the Sheets API into Drive. Folder
# membership is a Drive file-level concept; we expose it here so the same
# six verbs work uniformly on it. Keys in `.parents.FID` are Drive folder
# IDs.


def _parents_get(client, target, _data):
    assert target.spreadsheet_id is not None
    key = target.property.key if target.property else None
    parents = client.get_parents(target.spreadsheet_id)
    if key is None:
        return parents
    # Keyed get is a membership test — return the id if present, else raise
    # (mirrors `.named.NAME` behaviour so callers can rely on missing-key
    # being an explicit error rather than a silent empty result).
    if key in parents:
        return key
    raise GrammarError(f"folder {key!r} is not a parent of {target.spreadsheet_id}")


def _parents_as_list(data: Any) -> List[str]:
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        if not all(isinstance(x, str) for x in data):
            raise GrammarError("parents list must contain folder-ID strings")
        return list(data)
    raise GrammarError(
        f"parents value must be a folder ID string or list of strings, got {type(data).__name__}"
    )


def _parents_put(client, target, data):
    """Replace the parent set with the supplied folder IDs."""
    assert target.spreadsheet_id is not None
    new_parents = _parents_as_list(data)
    if not new_parents:
        raise GrammarError("put .parents requires at least one folder ID")
    existing = client.get_parents(target.spreadsheet_id)
    add = [p for p in new_parents if p not in existing]
    remove = [p for p in existing if p not in new_parents]
    return client.update_parents(target.spreadsheet_id, add=add, remove=remove)


def _parents_new(client, target, data):
    """Append folder(s) to the parent set (Drive supports multi-parent)."""
    assert target.spreadsheet_id is not None
    new_parents = _parents_as_list(data)
    if not new_parents:
        raise GrammarError("new .parents requires a folder ID")
    return client.update_parents(target.spreadsheet_id, add=new_parents)


def _parents_del(client, target, _data):
    """Remove one (keyed) or all (unkeyed) parents.

    Unkeyed deletion strips every parent — the file becomes orphaned in
    Drive's root, which is rarely what you want. We surface it as an
    error so the caller has to be explicit (``del SID.parents.FID`` for
    targeted removal, or ``put`` to replace the set).
    """
    assert target.spreadsheet_id is not None
    key = target.property.key if target.property else None
    if key is None:
        raise GrammarError(
            "del .parents requires a folder ID (would orphan the file); "
            "use del SID.parents.FOLDER_ID"
        )
    existing = client.get_parents(target.spreadsheet_id)
    if key not in existing:
        raise GrammarError(f"folder {key!r} is not a parent of {target.spreadsheet_id}")
    return client.update_parents(target.spreadsheet_id, remove=[key])


register(
    "parents", TargetType.SPREADSHEET,
    get=_parents_get, put=_parents_put, new=_parents_new, del_=_parents_del,
)


# ==========================================================================
# public helpers
# ==========================================================================


def supported(scope: TargetType) -> List[str]:
    """Return property names registered for ``scope`` (for --help / docs)."""
    return sorted({name for (name, sc) in _REGISTRY if sc == scope})
