"""Target-string grammar for the unified sheet-cli.

A target addresses any resource inside (or across) Google Spreadsheets:

    SID                       # a spreadsheet (whole)
    SID:Sheet                 # a sheet within that spreadsheet
    SID:Sheet!A1:B10          # a range within that sheet
    SID:Sheet!A1              # a cell (degenerate range)
    SID:Sheet!5               # row 5 (a dimension)
    SID:Sheet!C               # column C (a dimension)
    SID:!A1:B10               # range in the first sheet (default)

Any target above may be suffixed with ``.property`` to name a property of
the resource (format, freeze, named ranges, conditional rules, etc.):

    SID.title                 # spreadsheet-level property
    SID.named.sales           # element of a collection (by key)
    SID:Sheet.freeze          # sheet-level property
    SID:Sheet.conditional[0]  # element of a collection (by index)
    SID:Sheet!A1:B2.format    # range-level property
    SID:Sheet!5.height        # dimension-level property

For the second operand of binary verbs (copy / move), any part of the target
may be omitted; the missing parts are inherited from the first operand:

    Sheet!A1                  # inherit SID, use Sheet + A1
    !A1                       # inherit SID AND sheet, use A1
    :Sheet!A1                 # explicit-empty SID (equivalent to above's SID case)
    :Sheet                    # inherit SID, sheet-level target

Sheet names containing ':', '!', or '.' must be single-quoted: 'My:Sheet'!A1.
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
class PropertyRef:
    """A named property of a target resource, optionally keyed.

    Collections are addressed by key: ``named.sales`` -> ``PropertyRef("named",
    "sales")``; ``conditional[0]`` -> ``PropertyRef("conditional", "0")``. The
    key is kept as an opaque string; handlers decide how to interpret it.
    """
    name: str
    key: Optional[str] = None

    def render(self) -> str:
        if self.key is None:
            return self.name
        # Bracket notation for numeric keys and keys containing '.' / '['.
        if self.key.isdigit() or any(c in self.key for c in ".[]"):
            return f"{self.name}[{self.key}]"
        return f"{self.name}.{self.key}"


@dataclass(frozen=True)
class ParsedTarget:
    """A target string after parsing; any component may be None."""
    # NOTE: ``is_empty`` is declared before the ``property`` field because a
    # dataclass field named ``property`` shadows the builtin @property inside
    # the class body.
    @property
    def is_empty(self) -> bool:
        return (
            self.spreadsheet_id is None
            and self.sheet is None
            and self.locator is None
            and self.property is None
        )

    spreadsheet_id: Optional[str] = None
    sheet: Optional[str] = None
    locator: Optional[str] = None
    property: Optional[PropertyRef] = None


@dataclass(frozen=True)
class Target:
    """A fully-resolved target. spreadsheet_id is None only for DRIVE."""
    spreadsheet_id: Optional[str]
    sheet: Optional[str]
    locator: Optional[str]
    property: Optional[PropertyRef] = None


class GrammarError(ValueError):
    """Raised for unparseable or unresolvable target strings."""


_A1_RANGE_RE = re.compile(r"^[A-Z]+\d*(?::[A-Z]+\d*)?$|^\d+(?::\d+)?$|^[A-Z]+:[A-Z]+$")
_ROW_RE = re.compile(r"^\d+$")
_COL_RE = re.compile(r"^[A-Z]+$")
_CELL_RE = re.compile(r"^[A-Z]+\d+$")
_PROPERTY_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _split_unquoted(s: str, sep: str) -> tuple[str, Optional[str]]:
    """Split at the first `sep` outside single quotes.

    Returns ``(left, right)``; ``right`` is None when the separator is absent.
    """
    in_quote = False
    for i, ch in enumerate(s):
        if ch == "'":
            in_quote = not in_quote
        elif ch == sep and not in_quote:
            return s[:i], s[i + 1:]
    return s, None


def _split_identifier(identifier: str) -> tuple[Optional[str], Optional[str]]:
    """Split the identifier portion (left of '!') into (spreadsheet_id, sheet).

    Handles quoted sheet names ('My:Sheet').
    """
    if identifier == "":
        return None, None

    left, right = _split_unquoted(identifier, ':')
    if right is None:
        return identifier, None

    sid = left or None
    sheet = right or None
    if sheet is not None:
        sheet = _unquote_sheet(sheet)
    return sid, sheet


def _unquote_sheet(sheet: str) -> str:
    """Strip outer single quotes and collapse doubled inner quotes (Sheets style)."""
    if len(sheet) >= 2 and sheet.startswith("'") and sheet.endswith("'"):
        return sheet[1:-1].replace("''", "'")
    return sheet


def _has_unquoted_colon(s: str) -> bool:
    in_quote = False
    for ch in s:
        if ch == "'":
            in_quote = not in_quote
        elif ch == ':' and not in_quote:
            return True
    return False


def _parse_property_suffix(s: str) -> PropertyRef:
    """Parse the substring after the first unquoted '.' into a PropertyRef."""
    if not s:
        raise GrammarError("empty property suffix")

    # Bracket notation: name[key]
    if '[' in s:
        bracket = s.index('[')
        name = s[:bracket]
        if not s.endswith(']'):
            raise GrammarError(f"invalid property syntax: {s!r} (missing ']')")
        key = s[bracket + 1:-1]
        if not name or not _PROPERTY_NAME_RE.match(name):
            raise GrammarError(f"invalid property name: {name!r}")
        if key == "":
            raise GrammarError(f"empty key in {s!r}")
        return PropertyRef(name, key)

    # Dotted notation: name.key (or plain name)
    name, key = s.split('.', 1) if '.' in s else (s, None)
    if not _PROPERTY_NAME_RE.match(name):
        raise GrammarError(f"invalid property name: {name!r}")
    if key is not None and key == "":
        raise GrammarError(f"empty key after '.' in {s!r}")
    return PropertyRef(name, key)


def parse(target: str) -> ParsedTarget:
    """Parse a target string into a ParsedTarget.

    Does not resolve inheritance; any omitted component is None.
    """
    if target == "":
        return ParsedTarget()

    # Property suffix comes off first. '.' is never legal inside SID / locator
    # (and quoted sheet names mask their own '.'), so the first unquoted '.'
    # cleanly marks the boundary.
    head, prop_str = _split_unquoted(target, '.')
    property_ref = _parse_property_suffix(prop_str) if prop_str is not None else None

    if head == "":
        # Bare ".property" is not a valid target — property needs a resource.
        if property_ref is not None:
            raise GrammarError(f"property {property_ref.render()!r} has no target resource")
        return ParsedTarget()

    identifier, locator = _split_unquoted(head, '!')
    sid, sheet = _split_identifier(identifier)

    if locator is not None and locator == "":
        raise GrammarError(f"empty locator after '!' in {target!r}")

    if locator is None and sid is None and sheet is None and property_ref is None:
        return ParsedTarget()

    # When '!' was present but identifier has no unquoted ':', the identifier
    # is a sheet name (possibly quoted), not a SID — the user is leaving SID
    # to be inherited.
    bang_present = locator is not None
    if bang_present and sid is not None and sheet is None and not _has_unquoted_colon(identifier):
        sid, sheet = None, _unquote_sheet(sid)

    return ParsedTarget(
        spreadsheet_id=sid,
        sheet=sheet,
        locator=locator,
        property=property_ref,
    )


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

    return Target(
        spreadsheet_id=sid,
        sheet=sheet,
        locator=locator,
        property=child.property,
    )


def classify(target: Target) -> TargetType:
    """Classify a resolved Target by its resource shape.

    Properties don't change the resource type — ``SID:Sheet.freeze`` still
    classifies as SHEET. The property layer looks up handlers by (name, type).
    """
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
    # _A1_RANGE_RE covers both 'A1' and 'A1:B2' forms.
    if _A1_RANGE_RE.match(loc):
        return TargetType.RANGE
    raise GrammarError(f"cannot classify locator {loc!r}")


def is_single_cell(target: Target) -> bool:
    """Return True iff target is a single-cell RANGE like 'A1' (not 'A1:B2')."""
    if target.locator is None:
        return False
    return bool(_CELL_RE.match(target.locator))


def render(target: Target) -> str:
    """Render a Target back to canonical string form (inverse of parse)."""
    parts: list[str] = []
    if target.spreadsheet_id is not None:
        parts.append(target.spreadsheet_id)
        if target.sheet is not None or target.locator is not None:
            parts.append(":")
            if target.sheet is not None:
                sheet = target.sheet
                if any(c in sheet for c in ":!.'"):
                    # Escape embedded single quotes by doubling (Sheets-API style).
                    sheet = "'" + sheet.replace("'", "''") + "'"
                parts.append(sheet)
            if target.locator is not None:
                parts.append("!")
                parts.append(target.locator)
    if target.property is not None:
        parts.append(".")
        parts.append(target.property.render())
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
    if any(c in sheet for c in " !:'."):
        # Escape any embedded single quotes by doubling them (Google Sheets style).
        escaped = sheet.replace("'", "''")
        return f"'{escaped}'"
    return sheet


def with_sheet(target: Target, sheet: str) -> Target:
    """Return a copy of target with sheet filled in (used when defaulting to first sheet)."""
    return replace(target, sheet=sheet)
