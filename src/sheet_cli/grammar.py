"""Target-string grammar for the unified sheet-cli.

A target addresses any resource inside (or across) Google Spreadsheets:

    SID                       # a spreadsheet (whole)
    SID:Sheet                 # a sheet within that spreadsheet
    SID:Sheet!A1:B10          # a range within that sheet
    SID:Sheet!A1              # a cell (degenerate range)
    SID:Sheet!5               # row 5 (a dimension)
    SID:Sheet!C               # column C (a dimension)
    SID:!A1:B10               # range in the first sheet (default)

For the second operand of binary verbs (copy / move), any part of the target
may be omitted; the missing parts are inherited from the first operand:

    Sheet!A1                  # inherit SID, use Sheet + A1
    !A1                       # inherit SID AND sheet, use A1
    :Sheet!A1                 # explicit-empty SID (equivalent to above's SID case)
    :Sheet                    # inherit SID, sheet-level target

Sheet names containing ':' or '!' must be single-quoted: 'My:Sheet'!A1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class TargetType(Enum):
    DRIVE = "drive"                # no target — Drive-level listing
    SPREADSHEET = "spreadsheet"
    SHEET = "sheet"
    RANGE = "range"
    ROW = "row"
    COLUMN = "column"


@dataclass(frozen=True)
class ParsedTarget:
    """A target string after parsing; any component may be None."""
    spreadsheet_id: Optional[str] = None
    sheet: Optional[str] = None
    locator: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.spreadsheet_id is None and self.sheet is None and self.locator is None


@dataclass(frozen=True)
class Target:
    """A fully-resolved target. spreadsheet_id is None only for DRIVE."""
    spreadsheet_id: Optional[str]
    sheet: Optional[str]
    locator: Optional[str]


class GrammarError(ValueError):
    """Raised for unparseable or unresolvable target strings."""


_A1_RANGE_RE = re.compile(r"^[A-Z]+\d*(?::[A-Z]+\d*)?$|^\d+(?::\d+)?$|^[A-Z]+:[A-Z]+$")
_ROW_RE = re.compile(r"^\d+$")
_COL_RE = re.compile(r"^[A-Z]+$")
_CELL_RE = re.compile(r"^[A-Z]+\d+$")


def _split_identifier(identifier: str) -> tuple[Optional[str], Optional[str]]:
    """Split the identifier portion (left of '!') into (spreadsheet_id, sheet).

    Handles quoted sheet names ('My:Sheet').
    """
    if identifier == "":
        return None, None

    # Check for quoted sheet name format: SID:'Quoted:Name' or 'Quoted:Name'
    # We look for ':' that is NOT inside single quotes.
    in_quote = False
    split_at = -1
    for i, ch in enumerate(identifier):
        if ch == "'":
            in_quote = not in_quote
        elif ch == ':' and not in_quote:
            split_at = i
            break

    if split_at < 0:
        # No unquoted colon — the whole identifier is either a SID or a sheet.
        return identifier, None

    sid = identifier[:split_at] or None
    sheet = identifier[split_at + 1:] or None
    if sheet is not None:
        sheet = _unquote_sheet(sheet)
    return sid, sheet


def _unquote_sheet(sheet: str) -> str:
    if len(sheet) >= 2 and sheet.startswith("'") and sheet.endswith("'"):
        return sheet[1:-1]
    return sheet


def _split_on_first_bang(s: str) -> tuple[str, Optional[str]]:
    """Split at the first '!' that is NOT inside single quotes."""
    in_quote = False
    for i, ch in enumerate(s):
        if ch == "'":
            in_quote = not in_quote
        elif ch == '!' and not in_quote:
            return s[:i], s[i + 1:]
    return s, None


def parse(target: str) -> ParsedTarget:
    """Parse a target string into a ParsedTarget.

    Does not resolve inheritance; any omitted component is None.
    """
    if target == "":
        return ParsedTarget()

    identifier, locator = _split_on_first_bang(target)
    sid, sheet = _split_identifier(identifier)

    if locator is not None and locator == "":
        raise GrammarError(f"empty locator after '!' in {target!r}")

    if locator is None and sid is None and sheet is None:
        return ParsedTarget()

    # When '!' was present but identifier has no unquoted ':', the identifier
    # is a sheet name (possibly quoted), not a SID — the user is leaving SID
    # to be inherited.
    bang_present = locator is not None
    if bang_present and sid is not None and sheet is None and not _has_unquoted_colon(identifier):
        sid, sheet = None, _unquote_sheet(sid)

    return ParsedTarget(spreadsheet_id=sid, sheet=sheet, locator=locator)


def _has_unquoted_colon(s: str) -> bool:
    in_quote = False
    for ch in s:
        if ch == "'":
            in_quote = not in_quote
        elif ch == ':' and not in_quote:
            return True
    return False


def resolve(parent: Optional[Target], child: ParsedTarget) -> Target:
    """Resolve a ParsedTarget into a Target, inheriting from parent when needed.

    If parent is None, any missing spreadsheet_id is an error (unless the
    result is DRIVE — i.e. fully empty).
    """
    if child.is_empty:
        return Target(spreadsheet_id=None, sheet=None, locator=None)

    sid = child.spreadsheet_id
    sheet = child.sheet
    locator = child.locator

    if sid is None:
        if parent is None or parent.spreadsheet_id is None:
            raise GrammarError("spreadsheet_id is required (cannot inherit)")
        sid = parent.spreadsheet_id

    if sheet is None and locator is not None:
        # A locator without a sheet needs a sheet — inherit if possible,
        # otherwise leave None and let the verb layer substitute the first
        # sheet of the spreadsheet.
        if parent is not None and parent.sheet is not None:
            sheet = parent.sheet

    return Target(spreadsheet_id=sid, sheet=sheet, locator=locator)


def classify(target: Target) -> TargetType:
    """Classify a resolved Target by its resource shape."""
    if target.spreadsheet_id is None:
        return TargetType.DRIVE
    if target.locator is None:
        if target.sheet is None:
            return TargetType.SPREADSHEET
        return TargetType.SHEET
    loc = target.locator
    if _ROW_RE.match(loc):
        return TargetType.ROW
    if _COL_RE.match(loc):
        return TargetType.COLUMN
    if _A1_RANGE_RE.match(loc) or _CELL_RE.match(loc):
        return TargetType.RANGE
    raise GrammarError(f"cannot classify locator {loc!r}")


def render(target: Target) -> str:
    """Render a Target back to canonical string form (inverse of parse)."""
    if target.spreadsheet_id is None:
        return ""
    parts = [target.spreadsheet_id]
    if target.sheet is not None or target.locator is not None:
        parts.append(":")
        if target.sheet is not None:
            sheet = target.sheet
            if ":" in sheet or "!" in sheet:
                sheet = f"'{sheet}'"
            parts.append(sheet)
        if target.locator is not None:
            parts.append("!")
            parts.append(target.locator)
    return "".join(parts)


def a1_range_for_locator(target: Target) -> str:
    """Build an A1-notation range string suitable for values.get / values.batchUpdate.

    Sheet name is quoted when necessary. If sheet is None, returns the bare
    locator (API will use the first sheet).
    """
    if target.locator is None:
        if target.sheet is None:
            raise GrammarError("no locator and no sheet — cannot build A1 range")
        return _quote_sheet_if_needed(target.sheet)
    if target.sheet is None:
        return target.locator
    return f"{_quote_sheet_if_needed(target.sheet)}!{target.locator}"


def _quote_sheet_if_needed(sheet: str) -> str:
    if any(c in sheet for c in " !:'"):
        # Escape any embedded single quotes by doubling them (Google Sheets style).
        escaped = sheet.replace("'", "''")
        return f"'{escaped}'"
    return sheet


def with_sheet(target: Target, sheet: str) -> Target:
    """Return a copy of target with sheet filled in (used when defaulting to first sheet)."""
    return replace(target, sheet=sheet)
