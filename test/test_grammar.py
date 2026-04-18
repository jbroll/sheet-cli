"""Tests for the target-string grammar module."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli.grammar import (
    GrammarError,
    ParsedTarget,
    PropertyRef,
    Target,
    TargetType,
    a1_range_for_locator,
    classify,
    parse,
    render,
    resolve,
)


class TestParseBasic:
    def test_empty(self):
        assert parse("") == ParsedTarget()

    def test_sid_only(self):
        assert parse("SID123") == ParsedTarget(spreadsheet_id="SID123")

    def test_sid_colon_sheet(self):
        assert parse("SID:Sheet1") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1"
        )

    def test_sid_colon_sheet_bang_range(self):
        assert parse("SID:Sheet1!A1:B10") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="A1:B10"
        )

    def test_sid_colon_sheet_bang_cell(self):
        assert parse("SID:Sheet1!A1") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="A1"
        )

    def test_sid_colon_sheet_bang_row(self):
        assert parse("SID:Sheet1!5") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="5"
        )

    def test_sid_colon_sheet_bang_col(self):
        assert parse("SID:Sheet1!C") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="C"
        )

    def test_sid_colon_empty_bang_range(self):
        # SID:!A1:B10 — explicit-empty sheet, inherit from default (first sheet)
        assert parse("SID:!A1:B10") == ParsedTarget(
            spreadsheet_id="SID", sheet=None, locator="A1:B10"
        )


class TestParseInheritance:
    """Second-operand short forms for binary verbs."""

    def test_sheet_bang_cell(self):
        # "Sheet1!A1" — bare identifier + '!' means it's a sheet name, not SID.
        assert parse("Sheet1!A1") == ParsedTarget(
            spreadsheet_id=None, sheet="Sheet1", locator="A1"
        )

    def test_bang_cell_only(self):
        # "!A1" — no SID, no sheet
        assert parse("!A1") == ParsedTarget(
            spreadsheet_id=None, sheet=None, locator="A1"
        )

    def test_colon_sheet_bang_cell(self):
        # ":Sheet1!A1" — explicit-empty SID, sheet + locator
        assert parse(":Sheet1!A1") == ParsedTarget(
            spreadsheet_id=None, sheet="Sheet1", locator="A1"
        )

    def test_colon_sheet_only(self):
        # ":Sheet1" — explicit-empty SID, sheet-level
        assert parse(":Sheet1") == ParsedTarget(
            spreadsheet_id=None, sheet="Sheet1"
        )


class TestParseQuoted:
    def test_quoted_sheet_with_colon(self):
        assert parse("SID:'My:Sheet'!A1") == ParsedTarget(
            spreadsheet_id="SID", sheet="My:Sheet", locator="A1"
        )

    def test_quoted_sheet_with_bang(self):
        assert parse("SID:'Weird!Name'!A1") == ParsedTarget(
            spreadsheet_id="SID", sheet="Weird!Name", locator="A1"
        )

    def test_quoted_sheet_no_sid(self):
        assert parse("'My:Sheet'!A1") == ParsedTarget(
            spreadsheet_id=None, sheet="My:Sheet", locator="A1"
        )


class TestParseErrors:
    def test_empty_locator_after_bang(self):
        with pytest.raises(GrammarError):
            parse("SID:Sheet1!")


class TestResolve:
    def test_resolve_empty_child_returns_drive(self):
        parent = Target(spreadsheet_id="P", sheet="S", locator="A1")
        result = resolve(parent, ParsedTarget())
        assert result == Target(None, None, None)

    def test_resolve_inherit_sid(self):
        parent = Target(spreadsheet_id="P", sheet="S", locator="A1")
        result = resolve(parent, ParsedTarget(sheet="T", locator="B2"))
        assert result == Target("P", "T", "B2")

    def test_resolve_inherit_sid_and_sheet(self):
        parent = Target(spreadsheet_id="P", sheet="S", locator="A1")
        result = resolve(parent, ParsedTarget(locator="B2"))
        assert result == Target("P", "S", "B2")

    def test_resolve_no_parent_missing_sid_errors(self):
        with pytest.raises(GrammarError):
            resolve(None, ParsedTarget(sheet="S"))

    def test_resolve_explicit_sid_overrides_parent(self):
        parent = Target(spreadsheet_id="P", sheet="S", locator="A1")
        result = resolve(parent, ParsedTarget(spreadsheet_id="Q", sheet="T"))
        assert result == Target("Q", "T", None)


class TestClassify:
    def test_drive(self):
        assert classify(Target(None, None, None)) == TargetType.DRIVE

    def test_spreadsheet(self):
        assert classify(Target("SID", None, None)) == TargetType.SPREADSHEET

    def test_sheet(self):
        assert classify(Target("SID", "Sheet1", None)) == TargetType.SHEET

    def test_range(self):
        assert classify(Target("SID", "Sheet1", "A1:B10")) == TargetType.RANGE

    def test_cell_is_range(self):
        assert classify(Target("SID", "Sheet1", "A1")) == TargetType.RANGE

    def test_row(self):
        assert classify(Target("SID", "Sheet1", "5")) == TargetType.ROW

    def test_column(self):
        assert classify(Target("SID", "Sheet1", "C")) == TargetType.COLUMN

    def test_full_col_range(self):
        assert classify(Target("SID", "Sheet1", "A:B")) == TargetType.RANGE

    def test_full_row_range(self):
        assert classify(Target("SID", "Sheet1", "1:3")) == TargetType.RANGE

    def test_unclassifiable_raises(self):
        with pytest.raises(GrammarError):
            classify(Target("SID", "Sheet1", "bogus-!"))


class TestRender:
    def test_empty(self):
        assert render(Target(None, None, None)) == ""

    def test_sid_only(self):
        assert render(Target("SID", None, None)) == "SID"

    def test_sid_sheet(self):
        assert render(Target("SID", "Sheet1", None)) == "SID:Sheet1"

    def test_sid_sheet_locator(self):
        assert render(Target("SID", "Sheet1", "A1:B10")) == "SID:Sheet1!A1:B10"

    def test_sid_no_sheet_with_locator(self):
        # Represents SID:!A1 — explicit-empty sheet.
        assert render(Target("SID", None, "A1")) == "SID:!A1"

    def test_quoted_sheet_with_colon(self):
        assert render(Target("SID", "My:Sheet", "A1")) == "SID:'My:Sheet'!A1"

    def test_quoted_sheet_with_bang(self):
        assert render(Target("SID", "Odd!Name", "A1")) == "SID:'Odd!Name'!A1"


class TestRoundTrip:
    @pytest.mark.parametrize("s", [
        "",
        "SID",
        "SID:Sheet1",
        "SID:Sheet1!A1",
        "SID:Sheet1!A1:B10",
        "SID:Sheet1!5",
        "SID:Sheet1!C",
        "SID:!A1:B10",
        "SID:'My:Sheet'!A1",
    ])
    def test_round_trip(self, s):
        parsed = parse(s)
        # Resolve with no parent when possible; only strings with a SID.
        if parsed.spreadsheet_id is not None or parsed.is_empty:
            t = Target(parsed.spreadsheet_id, parsed.sheet, parsed.locator)
            assert render(t) == s


class TestA1RangeForLocator:
    def test_simple(self):
        assert a1_range_for_locator(Target("SID", "Sheet1", "A1:B10")) == "Sheet1!A1:B10"

    def test_sheet_only(self):
        assert a1_range_for_locator(Target("SID", "Sheet1", None)) == "Sheet1"

    def test_bare_locator_no_sheet(self):
        assert a1_range_for_locator(Target("SID", None, "A1:B10")) == "A1:B10"

    def test_sheet_with_space_quoted(self):
        assert a1_range_for_locator(Target("SID", "My Sheet", "A1")) == "'My Sheet'!A1"

    def test_sheet_with_colon_quoted(self):
        assert a1_range_for_locator(Target("SID", "My:Sheet", "A1")) == "'My:Sheet'!A1"

    def test_sheet_with_quote_escaped(self):
        assert a1_range_for_locator(Target("SID", "Bob's", "A1")) == "'Bob''s'!A1"

    def test_no_locator_no_sheet_errors(self):
        with pytest.raises(GrammarError):
            a1_range_for_locator(Target("SID", None, None))


class TestPropertyParse:
    def test_spreadsheet_property(self):
        assert parse("SID.title") == ParsedTarget(
            spreadsheet_id="SID", property=PropertyRef("title")
        )

    def test_sheet_property(self):
        assert parse("SID:Sheet1.freeze") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1",
            property=PropertyRef("freeze"),
        )

    def test_range_property(self):
        assert parse("SID:Sheet1!A1:B2.format") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="A1:B2",
            property=PropertyRef("format"),
        )

    def test_row_property(self):
        assert parse("SID:Sheet1!5.height") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="5",
            property=PropertyRef("height"),
        )

    def test_col_property(self):
        assert parse("SID:Sheet1!C.width") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1", locator="C",
            property=PropertyRef("width"),
        )

    def test_collection_by_key_dot(self):
        assert parse("SID.named.sales") == ParsedTarget(
            spreadsheet_id="SID",
            property=PropertyRef("named", "sales"),
        )

    def test_collection_by_key_bracket(self):
        assert parse("SID:Sheet1.conditional[0]") == ParsedTarget(
            spreadsheet_id="SID", sheet="Sheet1",
            property=PropertyRef("conditional", "0"),
        )

    def test_collection_key_with_dot_uses_brackets(self):
        assert parse("SID.named[sales.2024]") == ParsedTarget(
            spreadsheet_id="SID",
            property=PropertyRef("named", "sales.2024"),
        )

    def test_bare_property_is_error(self):
        with pytest.raises(GrammarError):
            parse(".title")

    def test_empty_key_after_dot_is_error(self):
        with pytest.raises(GrammarError):
            parse("SID.named.")

    def test_empty_key_in_brackets_is_error(self):
        with pytest.raises(GrammarError):
            parse("SID.named[]")


class TestPropertyRender:
    def test_plain(self):
        assert PropertyRef("title").render() == "title"

    def test_dotted_key(self):
        assert PropertyRef("named", "sales").render() == "named.sales"

    def test_numeric_key_uses_brackets(self):
        assert PropertyRef("conditional", "0").render() == "conditional[0]"

    def test_dotted_value_uses_brackets(self):
        assert PropertyRef("named", "sales.2024").render() == "named[sales.2024]"

    def test_full_target_round_trip(self):
        target = Target("SID", "Sheet1", "A1:B2",
                        property=PropertyRef("format"))
        assert render(target) == "SID:Sheet1!A1:B2.format"

    def test_collection_round_trip(self):
        target = Target("SID", None, None,
                        property=PropertyRef("named", "sales"))
        assert render(target) == "SID.named.sales"


class TestPropertyResolve:
    def test_property_carried_through_resolve(self):
        parent = Target("SID", "Sheet1", None)
        child = parse(":Sheet2.freeze")
        resolved = resolve(parent, child)
        assert resolved.property == PropertyRef("freeze")
        assert resolved.sheet == "Sheet2"

    def test_classify_ignores_property(self):
        # Properties don't change the resource type.
        t = Target("SID", "Sheet1", None, property=PropertyRef("freeze"))
        assert classify(t) == TargetType.SHEET


class TestQuotedSheetWithDot:
    def test_sheet_with_dot_must_be_quoted_to_avoid_property(self):
        # 'My.Sheet' — quoted, so the dot is part of the sheet name.
        assert parse("SID:'My.Sheet'!A1") == ParsedTarget(
            spreadsheet_id="SID", sheet="My.Sheet", locator="A1"
        )

    def test_sheet_with_dot_round_trip_quoted(self):
        t = Target("SID", "My.Sheet", "A1")
        assert render(t) == "SID:'My.Sheet'!A1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
