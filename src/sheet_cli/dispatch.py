"""Binary verbs (copy, move) with server-side optimizations.

Dispatch table — picks the best API given the source and destination shapes:

  same spreadsheet, RANGE→RANGE  ─→  batchUpdate: copyPaste / cutPaste
  same spreadsheet, ROW/COL move ─→  batchUpdate: moveDimension
  cross spreadsheet, whole SHEET ─→  sheets.copyTo (server-side)
  cross spreadsheet, RANGE       ─→  client-side read + write fallback
  move across spreadsheets       ─→  copy + delete (never server-side)
"""

from __future__ import annotations

from typing import Any, Dict

from sheet_client import CellData, SheetsClient
from sheet_client.utils import a1_to_grid_range

from .grammar import (
    GrammarError,
    Target,
    TargetType,
    a1_range_for_locator,
    classify,
    render,
)
from .verbs import _locator_to_dimension_range, _resolve_sheet_id


def _grid_range(client: SheetsClient, target: Target) -> Dict[str, Any]:
    """Build a GridRange dict for a RANGE target (adds sheetId)."""
    assert target.spreadsheet_id is not None and target.sheet is not None
    sheet_id = _resolve_sheet_id(client, target.spreadsheet_id, target.sheet)
    loc = target.locator
    if loc is None:
        # whole sheet — no bounds
        return {"sheetId": sheet_id}
    # a1_to_grid_range expects Sheet!A1:B2 form
    gr = a1_to_grid_range(f"{target.sheet}!{loc}") if "!" not in loc else a1_to_grid_range(loc)
    gr["sheetId"] = sheet_id
    return gr


def do_copy(client: SheetsClient, source: Target, dest: Target) -> Dict[str, Any]:
    if source.property is not None or dest.property is not None:
        raise GrammarError("copy does not support .property targets")

    src_type = classify(source)
    dst_type = classify(dest)

    # Whole-spreadsheet copy (Drive ``files.copy``): source is a spreadsheet,
    # dest is either another "spreadsheet" (interpreted as the new title) or
    # bare DRIVE (default "Copy of ..." title). Copying onto itself would be
    # a no-op aliasing bug, so identical SIDs are rejected. Evaluated before
    # the "both SIDs required" guard so DRIVE dest (SID=None) is accepted.
    if src_type == TargetType.SPREADSHEET and dst_type in (TargetType.SPREADSHEET, TargetType.DRIVE):
        if source.spreadsheet_id is None:
            raise GrammarError("copy requires a spreadsheet ID on the source")
        if dst_type == TargetType.SPREADSHEET and source.spreadsheet_id == dest.spreadsheet_id:
            raise GrammarError("copy: source and destination spreadsheet IDs are the same")
        new_title = dest.spreadsheet_id if dst_type == TargetType.SPREADSHEET else None
        return client.copy_spreadsheet(source.spreadsheet_id, new_title=new_title)

    if source.spreadsheet_id is None or dest.spreadsheet_id is None:
        raise GrammarError("copy requires spreadsheet_id on both operands")

    same_ss = source.spreadsheet_id == dest.spreadsheet_id

    # Cross-spreadsheet whole-sheet copy — server-side.
    if src_type == TargetType.SHEET and dst_type == TargetType.SPREADSHEET and not same_ss:
        assert source.sheet is not None
        src_sheet_id = _resolve_sheet_id(client, source.spreadsheet_id, source.sheet)
        return client.copy_sheet_to(source.spreadsheet_id, src_sheet_id, dest.spreadsheet_id)

    # Same-spreadsheet range→range copy — server-side copyPaste.
    if same_ss and src_type == TargetType.RANGE and dst_type == TargetType.RANGE:
        src_grid = _grid_range(client, source)
        dst_grid = _grid_range(client, dest)
        return client.meta_write(source.spreadsheet_id, [{
            "copyPaste": {
                "source": src_grid,
                "destination": dst_grid,
                "pasteType": "PASTE_NORMAL",
            }
        }])

    # Fallback: read + write (formulas preserved).
    if src_type in (TargetType.RANGE, TargetType.SHEET) and dst_type in (TargetType.RANGE, TargetType.SHEET):
        src_a1 = a1_range_for_locator(source)
        response = client.read(source.spreadsheet_id, [src_a1],
                               types=CellData.VALUE | CellData.FORMULA)
        values = (response.get("values")
                  or (response.get("valueRanges", [{}])[0].get("values", [])))
        if not values:
            return {"copied": 0, "from": render(source), "to": render(dest)}
        dst_a1 = a1_range_for_locator(dest)
        client.write(dest.spreadsheet_id, [{"range": dst_a1, "values": values}])
        return {"copied": sum(len(r) for r in values), "from": render(source), "to": render(dest)}

    raise GrammarError(f"copy not supported for {src_type.value} → {dst_type.value}")


def do_move(client: SheetsClient, source: Target, dest: Target) -> Dict[str, Any]:
    if source.property is not None or dest.property is not None:
        raise GrammarError("move does not support .property targets")

    src_type = classify(source)
    dst_type = classify(dest)

    if source.spreadsheet_id is None or dest.spreadsheet_id is None:
        raise GrammarError("move requires spreadsheet_id on both operands")

    same_ss = source.spreadsheet_id == dest.spreadsheet_id

    # Same-sheet row/column move — server-side moveDimension.
    if (same_ss
            and src_type in (TargetType.ROW, TargetType.COLUMN)
            and dst_type == src_type
            and source.sheet == dest.sheet):
        assert source.sheet is not None
        sheet_id = _resolve_sheet_id(client, source.spreadsheet_id, source.sheet)
        src_range = _locator_to_dimension_range(source, sheet_id)
        dst_range = _locator_to_dimension_range(dest, sheet_id)
        return client.meta_write(source.spreadsheet_id, [{
            "moveDimension": {
                "source": src_range,
                "destinationIndex": dst_range["startIndex"],
            }
        }])

    # Same-spreadsheet range→range move — server-side cutPaste.
    if same_ss and src_type == TargetType.RANGE and dst_type == TargetType.RANGE:
        src_grid = _grid_range(client, source)
        dst_grid = _grid_range(client, dest)
        return client.meta_write(source.spreadsheet_id, [{
            "cutPaste": {
                "source": src_grid,
                "destination": dst_grid,
                "pasteType": "PASTE_NORMAL",
            }
        }])

    # Cross-spreadsheet — always copy + delete fallback.
    copy_result = do_copy(client, source, dest)
    if src_type == TargetType.SHEET:
        # Delete source sheet after copy.
        assert source.sheet is not None
        src_sheet_id = _resolve_sheet_id(client, source.spreadsheet_id, source.sheet)
        client.meta_write(source.spreadsheet_id, [{
            "deleteSheet": {"sheetId": src_sheet_id}
        }])
    elif src_type == TargetType.RANGE:
        client.clear(source.spreadsheet_id, [a1_range_for_locator(source)])
    return copy_result
