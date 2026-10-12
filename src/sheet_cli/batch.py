"""The ``batch`` verb's core: a list of operations -> values + batchUpdate requests.

Pure and testable. Sheet titles are resolved through an injected callable, so
tests pass a plain dict and the CLI passes a client-backed resolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from sheet_client.utils import a1_to_grid_range, column_to_index

from . import builders
from .grammar import GrammarError, parse

_LOCATORS = ("range", "row", "column")
_RANGE_ACTIONS = ("values", "clear", "format", "borders", "note", "merge", "validation")
_ALL_ACTIONS = (*_RANGE_ACTIONS, "width", "height")
_MERGE_TYPES = ("MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS")


@dataclass
class BatchPlan:
    values: List[Dict[str, Any]] = field(default_factory=list)
    clears: List[str] = field(default_factory=list)
    requests: List[Dict[str, Any]] = field(default_factory=list)


def _split_locator(locator: Any, where: str) -> Tuple[str, str]:
    """Split 'Sheet Title!A1:B2' into (sheet_title, local_locator)."""
    if not isinstance(locator, str) or "!" not in locator:
        raise GrammarError(f"{where}: locator must be 'Sheet!A1' form, got {locator!r}")
    parsed = parse(locator)
    if parsed.sheet is None or parsed.locator is None:
        raise GrammarError(f"{where}: locator needs a sheet and a range, got {locator!r}")
    return parsed.sheet, parsed.locator


def _column_dimension(sheet_id: int, col: str) -> Dict[str, Any]:
    idx = column_to_index(col)
    return {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1}


def _row_dimension(sheet_id: int, row: str) -> Dict[str, Any]:
    try:
        idx = int(row) - 1
    except (TypeError, ValueError):
        raise GrammarError(f"row locator must be a number, got {row!r}")
    return {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": idx, "endIndex": idx + 1}


def _merge_type(value: Any) -> str:
    if value is True:
        return "MERGE_ALL"
    if isinstance(value, str) and value.upper() in _MERGE_TYPES:
        return value.upper()
    raise GrammarError(f"merge must be true or one of {_MERGE_TYPES}, got {value!r}")


def build_batch(ops: Any, resolve_sheet_id: Callable[[str], int]) -> BatchPlan:
    """Turn a list of operation objects into a BatchPlan.

    Each op has exactly one locator (``range``, ``row``, or ``column``) naming a
    sheet, and at least one action. Actions on a ``range`` locator: values,
    clear, format, borders, note, merge, validation. ``width`` needs a column
    locator; ``height`` needs a row locator.
    """
    if not isinstance(ops, list):
        raise GrammarError("batch payload must be a JSON array of operations")

    plan = BatchPlan()
    cache: Dict[str, int] = {}

    def sid_for(sheet: str) -> int:
        if sheet not in cache:
            cache[sheet] = resolve_sheet_id(sheet)
        return cache[sheet]

    for i, op in enumerate(ops):
        where = f"op {i}"
        if not isinstance(op, dict):
            raise GrammarError(f"{where}: must be a JSON object")

        locators = [k for k in _LOCATORS if k in op]
        if len(locators) != 1:
            raise GrammarError(f"{where}: exactly one of {_LOCATORS} is required")
        loc = locators[0]

        actions = [k for k in _ALL_ACTIONS if k in op and (k != "clear" or op[k])]
        if not actions:
            raise GrammarError(f"{where}: no action (one of {_ALL_ACTIONS} is required)")

        sheet, local = _split_locator(op[loc], where)

        for act in actions:
            if act == "width":
                if loc != "column":
                    raise GrammarError(f"{where}: width requires a column locator")
                plan.requests.append(
                    builders.dimension_request(_column_dimension(sid_for(sheet), local), int(op[act]))
                )
                continue
            if act == "height":
                if loc != "row":
                    raise GrammarError(f"{where}: height requires a row locator")
                plan.requests.append(
                    builders.dimension_request(_row_dimension(sid_for(sheet), local), int(op[act]))
                )
                continue
            if loc != "range":
                raise GrammarError(f"{where}: {act} requires a range locator")
            if act == "values":
                plan.values.append({"range": op[loc], "values": op["values"]})
                continue
            if act == "clear":
                plan.clears.append(op[loc])
                continue
            grid = a1_to_grid_range(local, sheet_id=sid_for(sheet))
            if act == "format":
                plan.requests.append(builders.format_request(grid, op["format"]))
            elif act == "borders":
                plan.requests.append(builders.borders_request(grid, op["borders"]))
            elif act == "note":
                plan.requests.append(builders.note_request(grid, op["note"]))
            elif act == "validation":
                plan.requests.append(builders.validation_request(grid, op["validation"]))
            elif act == "merge":
                plan.requests.append(builders.merge_request(grid, _merge_type(op["merge"])))

    return plan
