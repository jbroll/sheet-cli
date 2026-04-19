"""Tests for the property handler registry.

Uses mocked SheetsClient to verify the batchUpdate payloads we emit match
the Google Sheets REST API shape. Each handler is exercised through
`properties.dispatch(...)` so the wiring from verb → registry → handler
is also covered.
"""

import os
import sys

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sheet_cli.grammar import GrammarError, PropertyRef, Target, TargetType
from sheet_cli.properties import dispatch, supported


def _client(meta=None, write_reply=None, read_reply=None):
    c = MagicMock()
    c.meta_read.return_value = meta or {
        "properties": {"title": "TestBook"},
        "sheets": [{
            "properties": {
                "sheetId": 42, "title": "Sheet1",
                "gridProperties": {
                    "frozenRowCount": 0, "frozenColumnCount": 0,
                    "rowCount": 100, "columnCount": 26,
                },
            },
        }],
    }
    c.meta_write.return_value = write_reply or {"ok": True}
    # Grid reads match spreadsheets.get(includeGridData=True): the response
    # has every sheet in the book, and only those touched by ``ranges`` carry
    # a populated ``data`` block. Handlers must pick out the target sheet by
    # title — they cannot blindly use ``sheets[0]``.
    c.read.return_value = read_reply or {
        "sheets": [{
            "properties": {"sheetId": 42, "title": "Sheet1"},
            "data": [{
                "rowData": [
                    {"values": [
                        {"userEnteredFormat": {"backgroundColor": {"red": 1.0}}},
                        {"userEnteredFormat": {}},
                    ]},
                ],
                "rowMetadata": [{"pixelSize": 25}],
                "columnMetadata": [{"pixelSize": 120}],
            }],
        }],
    }
    return c


def _target(sid="SID", sheet="Sheet1", locator=None, prop_name=None, key=None):
    prop = PropertyRef(prop_name, key) if prop_name else None
    return Target(sid, sheet, locator, prop)


# ---------------------------- registry ----------------------------


class TestRegistry:
    def test_supported_range(self):
        names = supported(TargetType.RANGE)
        assert set(names) >= {"format", "borders", "merge", "note", "validation", "protected"}

    def test_supported_sheet(self):
        names = supported(TargetType.SHEET)
        assert set(names) >= {
            "freeze", "color", "hidden", "title", "conditional", "protected",
            "hideGridlines", "index", "rightToLeft", "rowCount", "columnCount", "filter",
        }

    def test_supported_spreadsheet(self):
        names = supported(TargetType.SPREADSHEET)
        assert set(names) >= {
            "title", "named", "parents",
            "locale", "timeZone", "autoRecalc", "theme", "defaultFormat", "iterativeCalc",
        }

    def test_supported_row(self):
        assert set(supported(TargetType.ROW)) >= {"height", "hidden", "autofit"}

    def test_supported_column(self):
        assert set(supported(TargetType.COLUMN)) >= {"width", "hidden", "autofit"}

    def test_unknown_property_raises(self):
        c = _client()
        t = _target(locator="A1", prop_name="bogus")
        with pytest.raises(GrammarError, match="not valid"):
            dispatch("get", c, t, None)

    def test_unsupported_verb_raises(self):
        c = _client()
        # ROW.height has no del handler.
        t = Target("SID", "Sheet1", "5", PropertyRef("height"))
        with pytest.raises(GrammarError, match="is not supported"):
            dispatch("del", c, t, None)


# ---------------------------- range properties ----------------------------


class TestRangeFormat:
    def test_put_emits_repeatCell(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="format")
        dispatch("put", c, t, {"backgroundColor": {"red": 1.0}})
        req = c.meta_write.call_args[0][1][0]
        assert "repeatCell" in req
        rc = req["repeatCell"]
        assert rc["cell"] == {"userEnteredFormat": {"backgroundColor": {"red": 1.0}}}
        # Field mask is leaf-level so a partial update doesn't clobber siblings
        # (updating just the red channel must not erase green/blue).
        assert rc["fields"] == "userEnteredFormat.backgroundColor.red"
        assert rc["range"]["sheetId"] == 42

    def test_put_fields_mask_walks_to_leaves(self):
        """Nested format updates emit every leaf path — not the top-level key."""
        c = _client()
        t = _target(locator="A1:B2", prop_name="format")
        dispatch("put", c, t, {
            "textFormat": {"bold": True, "italic": True},
            "backgroundColor": {"red": 1.0, "green": 0.5},
        })
        fields = set(c.meta_write.call_args[0][1][0]["repeatCell"]["fields"].split(","))
        assert fields == {
            "userEnteredFormat.textFormat.bold",
            "userEnteredFormat.textFormat.italic",
            "userEnteredFormat.backgroundColor.red",
            "userEnteredFormat.backgroundColor.green",
        }

    def test_get_picks_target_sheet_when_book_has_many(self):
        """B1 regression: a grid read returns all sheets; must filter by title."""
        read_reply = {
            "sheets": [
                {  # unrelated — no data
                    "properties": {"sheetId": 1, "title": "Other"},
                },
                {
                    "properties": {"sheetId": 42, "title": "Sheet1"},
                    "data": [{"rowData": [{"values": [
                        {"userEnteredFormat": {"backgroundColor": {"red": 1.0}}},
                    ]}]}],
                },
            ],
        }
        meta = {
            "properties": {"title": "Book"},
            "sheets": [
                {"properties": {"sheetId": 1, "title": "Other"}},
                {"properties": {"sheetId": 42, "title": "Sheet1"}},
            ],
        }
        c = _client(meta=meta, read_reply=read_reply)
        t = _target(sheet="Sheet1", locator="A1", prop_name="format")
        result = dispatch("get", c, t, None)
        # Must get Sheet1's data, not the empty-data first entry.
        assert result == [[{"backgroundColor": {"red": 1.0}}]]

    def test_get_missing_sheet_raises(self):
        read_reply = {"sheets": [{"properties": {"sheetId": 1, "title": "Other"}}]}
        c = _client(read_reply=read_reply)
        t = _target(sheet="Ghost", locator="A1", prop_name="format")
        with pytest.raises(GrammarError, match="not found in grid response"):
            dispatch("get", c, t, None)

    def test_del_clears_userEnteredFormat(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="format")
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert req["repeatCell"]["fields"] == "userEnteredFormat"

    def test_put_rejects_non_dict(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="format")
        with pytest.raises(GrammarError):
            dispatch("put", c, t, "not a dict")


class TestRangeBorders:
    def test_del_uses_NONE_style(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="borders")
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        ub = req["updateBorders"]
        assert ub["top"] == {"style": "NONE"}
        assert ub["innerHorizontal"] == {"style": "NONE"}

    def test_put_forwards_body(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="borders")
        dispatch("put", c, t, {"top": {"style": "SOLID"}})
        req = c.meta_write.call_args[0][1][0]
        assert req["updateBorders"]["top"] == {"style": "SOLID"}


class TestRangeMerge:
    def test_new_mergeCells(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="merge")
        dispatch("new", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert "mergeCells" in req
        assert req["mergeCells"]["mergeType"] == "MERGE_ALL"

    def test_del_unmergeCells(self):
        c = _client()
        t = _target(locator="A1:B2", prop_name="merge")
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert "unmergeCells" in req

    def test_get_reads_from_grid_data(self):
        """B6 regression: merges live in grid-data blocks, not plain meta_read."""
        read_reply = {
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "data": [{}],
                "merges": [
                    {"sheetId": 42, "startRowIndex": 0, "endRowIndex": 2,
                     "startColumnIndex": 0, "endColumnIndex": 2},
                    # Non-overlapping: should not be returned.
                    {"sheetId": 42, "startRowIndex": 10, "endRowIndex": 12,
                     "startColumnIndex": 0, "endColumnIndex": 2},
                ],
            }],
        }
        c = _client(read_reply=read_reply)
        t = _target(locator="A1:B2", prop_name="merge")
        merges = dispatch("get", c, t, None)
        assert len(merges) == 1
        assert merges[0]["startRowIndex"] == 0


class TestRangeProtected:
    def _meta_with_protected(self, protected):
        return {
            "properties": {"title": "TB"},
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "protectedRanges": protected,
            }],
        }

    def test_del_removes_overlapping_ranges(self):
        protected = [
            {"protectedRangeId": 7, "range": {
                "sheetId": 42, "startRowIndex": 0, "endRowIndex": 5,
                "startColumnIndex": 0, "endColumnIndex": 5,
            }},
            # Non-overlapping — must NOT be touched.
            {"protectedRangeId": 9, "range": {
                "sheetId": 42, "startRowIndex": 20, "endRowIndex": 25,
                "startColumnIndex": 0, "endColumnIndex": 5,
            }},
        ]
        c = _client(meta=self._meta_with_protected(protected))
        t = _target(locator="A1:B2", prop_name="protected")
        dispatch("del", c, t, None)
        requests = c.meta_write.call_args[0][1]
        ids = [r["deleteProtectedRange"]["protectedRangeId"] for r in requests]
        assert ids == [7]

    def test_del_with_no_overlap_is_noop(self):
        c = _client(meta=self._meta_with_protected([]))
        t = _target(locator="A1:B2", prop_name="protected")
        result = dispatch("del", c, t, None)
        assert result == {"replies": []}
        assert not c.meta_write.called


class TestSheetProtected:
    def _meta(self, protected):
        return {
            "properties": {"title": "TB"},
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "protectedRanges": protected,
            }],
        }

    def test_put_empty_body_protects_whole_sheet(self):
        c = _client()
        t = _target(prop_name="protected")
        dispatch("put", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert req["addProtectedRange"]["protectedRange"] == {"range": {"sheetId": 42}}

    def test_put_with_unprotected_ranges(self):
        c = _client()
        t = _target(prop_name="protected")
        body = {
            "description": "Sheet protected except header",
            "warningOnly": False,
            "unprotectedRanges": [
                {"sheetId": 42, "startRowIndex": 0, "endRowIndex": 1},
            ],
        }
        dispatch("put", c, t, body)
        spec = c.meta_write.call_args[0][1][0]["addProtectedRange"]["protectedRange"]
        assert spec["range"] == {"sheetId": 42}  # whole-sheet form
        assert spec["description"] == "Sheet protected except header"
        assert spec["unprotectedRanges"] == body["unprotectedRanges"]

    def test_put_body_range_is_overwritten(self):
        # Users may copy/paste a ProtectedRange with an existing `range`;
        # we always force the whole-sheet form at this scope.
        c = _client()
        t = _target(prop_name="protected")
        dispatch("put", c, t, {"range": {"sheetId": 999, "startRowIndex": 5}})
        spec = c.meta_write.call_args[0][1][0]["addProtectedRange"]["protectedRange"]
        assert spec["range"] == {"sheetId": 42}

    def test_get_returns_only_whole_sheet_protections(self):
        protected = [
            {"protectedRangeId": 1, "range": {"sheetId": 42}},
            {"protectedRangeId": 2, "range": {
                "sheetId": 42, "startRowIndex": 0, "endRowIndex": 5,
            }},
            {"protectedRangeId": 3, "range": {"sheetId": 42},
             "unprotectedRanges": [{"sheetId": 42, "startRowIndex": 0, "endRowIndex": 1}]},
        ]
        c = _client(meta=self._meta(protected))
        t = _target(prop_name="protected")
        got = dispatch("get", c, t, None)
        assert [p["protectedRangeId"] for p in got] == [1, 3]

    def test_del_removes_only_whole_sheet_protections(self):
        protected = [
            {"protectedRangeId": 1, "range": {"sheetId": 42}},
            {"protectedRangeId": 2, "range": {
                "sheetId": 42, "startRowIndex": 0, "endRowIndex": 5,
            }},
            {"protectedRangeId": 3, "range": {"sheetId": 42},
             "unprotectedRanges": [{"sheetId": 42, "startRowIndex": 0, "endRowIndex": 1}]},
        ]
        c = _client(meta=self._meta(protected))
        t = _target(prop_name="protected")
        dispatch("del", c, t, None)
        ids = [
            r["deleteProtectedRange"]["protectedRangeId"]
            for r in c.meta_write.call_args[0][1]
        ]
        assert ids == [1, 3]

    def test_del_no_whole_sheet_protections_is_noop(self):
        protected = [{"protectedRangeId": 2, "range": {
            "sheetId": 42, "startRowIndex": 0, "endRowIndex": 5,
        }}]
        c = _client(meta=self._meta(protected))
        t = _target(prop_name="protected")
        result = dispatch("del", c, t, None)
        assert result == {"replies": []}
        assert not c.meta_write.called


class TestSheetScalars:
    """hideGridlines, index, rightToLeft, rowCount, columnCount."""

    def _meta(self, grid_props=None, extra=None):
        props = {
            "sheetId": 42, "title": "Sheet1", "index": 0,
            "gridProperties": grid_props or {"rowCount": 100, "columnCount": 26},
        }
        if extra:
            props.update(extra)
        return {
            "properties": {"title": "TB"},
            "sheets": [{"properties": props}],
        }

    def test_hideGridlines_put_true(self):
        c = _client()
        t = _target(prop_name="hideGridlines")
        dispatch("put", c, t, True)
        req = c.meta_write.call_args[0][1][0]["updateSheetProperties"]
        assert req["properties"]["gridProperties"]["hideGridlines"] is True
        assert req["fields"] == "gridProperties.hideGridlines"

    def test_hideGridlines_del_sets_false(self):
        c = _client()
        t = _target(prop_name="hideGridlines")
        dispatch("del", c, t, None)
        gp = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["gridProperties"]
        assert gp["hideGridlines"] is False

    def test_hideGridlines_get(self):
        c = _client(meta=self._meta(grid_props={"hideGridlines": True}))
        t = _target(prop_name="hideGridlines")
        assert dispatch("get", c, t, None) is True

    def test_hideGridlines_get_defaults_false(self):
        c = _client(meta=self._meta(grid_props={"rowCount": 100}))
        t = _target(prop_name="hideGridlines")
        assert dispatch("get", c, t, None) is False

    def test_index_put(self):
        c = _client()
        t = _target(prop_name="index")
        dispatch("put", c, t, 3)
        req = c.meta_write.call_args[0][1][0]["updateSheetProperties"]
        assert req["properties"]["index"] == 3
        assert req["fields"] == "index"

    def test_rightToLeft_put_bool(self):
        c = _client()
        t = _target(prop_name="rightToLeft")
        dispatch("put", c, t, "true")
        req = c.meta_write.call_args[0][1][0]["updateSheetProperties"]
        assert req["properties"]["rightToLeft"] is True
        assert req["fields"] == "rightToLeft"

    def test_rowCount_put(self):
        c = _client()
        t = _target(prop_name="rowCount")
        dispatch("put", c, t, 500)
        req = c.meta_write.call_args[0][1][0]["updateSheetProperties"]
        assert req["properties"]["gridProperties"]["rowCount"] == 500
        assert req["fields"] == "gridProperties.rowCount"

    def test_columnCount_put(self):
        c = _client()
        t = _target(prop_name="columnCount")
        dispatch("put", c, t, 40)
        req = c.meta_write.call_args[0][1][0]["updateSheetProperties"]
        assert req["properties"]["gridProperties"]["columnCount"] == 40
        assert req["fields"] == "gridProperties.columnCount"

    def test_rowCount_get(self):
        c = _client(meta=self._meta(grid_props={"rowCount": 250, "columnCount": 26}))
        assert dispatch("get", c, _target(prop_name="rowCount"), None) == 250


class TestSheetFilter:
    def _meta(self, basic_filter=None):
        props = {
            "sheetId": 42, "title": "Sheet1",
            "gridProperties": {"rowCount": 100, "columnCount": 26},
        }
        sheet = {"properties": props}
        if basic_filter is not None:
            sheet["basicFilter"] = basic_filter
        return {"properties": {"title": "TB"}, "sheets": [sheet]}

    def test_put_empty_body_defaults_range_to_whole_sheet(self):
        c = _client()
        t = _target(prop_name="filter")
        dispatch("put", c, t, None)
        req = c.meta_write.call_args[0][1][0]["setBasicFilter"]
        assert req["filter"]["range"] == {"sheetId": 42}

    def test_put_body_range_preserved(self):
        c = _client()
        t = _target(prop_name="filter")
        dispatch("put", c, t, {
            "range": {"sheetId": 42, "startRowIndex": 0, "endRowIndex": 10},
            "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}],
        })
        req = c.meta_write.call_args[0][1][0]["setBasicFilter"]
        assert req["filter"]["range"]["endRowIndex"] == 10
        assert req["filter"]["sortSpecs"][0]["sortOrder"] == "ASCENDING"

    def test_put_rejects_non_dict(self):
        c = _client()
        t = _target(prop_name="filter")
        with pytest.raises(GrammarError):
            dispatch("put", c, t, "oops")

    def test_del_emits_clearBasicFilter(self):
        c = _client()
        t = _target(prop_name="filter")
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert req == {"clearBasicFilter": {"sheetId": 42}}

    def test_get_returns_filter_when_present(self):
        bf = {"range": {"sheetId": 42}, "sortSpecs": []}
        c = _client(meta=self._meta(basic_filter=bf))
        t = _target(prop_name="filter")
        assert dispatch("get", c, t, None) == bf

    def test_get_returns_none_when_absent(self):
        c = _client(meta=self._meta())
        assert dispatch("get", c, _target(prop_name="filter"), None) is None


class TestDimHidden:
    def _grid(self, hidden_row=False, hidden_col=False):
        return {
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "data": [{
                    "rowMetadata": [{"hiddenByUser": hidden_row}],
                    "columnMetadata": [{"hiddenByUser": hidden_col}],
                    "rowData": [],
                }],
            }],
        }

    def test_row_hidden_put(self):
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("hidden"))
        dispatch("put", c, t, True)
        req = c.meta_write.call_args[0][1][0]["updateDimensionProperties"]
        assert req["range"]["dimension"] == "ROWS"
        assert req["range"]["startIndex"] == 4 and req["range"]["endIndex"] == 5
        assert req["properties"]["hiddenByUser"] is True
        assert req["fields"] == "hiddenByUser"

    def test_column_hidden_put(self):
        c = _client()
        t = Target("SID", "Sheet1", "C", PropertyRef("hidden"))
        dispatch("put", c, t, True)
        req = c.meta_write.call_args[0][1][0]["updateDimensionProperties"]
        assert req["range"]["dimension"] == "COLUMNS"
        assert req["range"]["startIndex"] == 2 and req["range"]["endIndex"] == 3

    def test_row_hidden_del_sets_false(self):
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("hidden"))
        dispatch("del", c, t, None)
        props = c.meta_write.call_args[0][1][0]["updateDimensionProperties"]["properties"]
        assert props["hiddenByUser"] is False

    def test_row_hidden_get(self):
        c = _client(read_reply=self._grid(hidden_row=True))
        t = Target("SID", "Sheet1", "5", PropertyRef("hidden"))
        assert dispatch("get", c, t, None) is True


class TestDimAutofit:
    def test_row_autofit_emits_autoResizeDimensions(self):
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("autofit"))
        dispatch("put", c, t, None)
        req = c.meta_write.call_args[0][1][0]["autoResizeDimensions"]
        assert req["dimensions"]["dimension"] == "ROWS"
        assert req["dimensions"]["startIndex"] == 4

    def test_column_autofit_emits_autoResizeDimensions(self):
        c = _client()
        t = Target("SID", "Sheet1", "C", PropertyRef("autofit"))
        dispatch("put", c, t, None)
        req = c.meta_write.call_args[0][1][0]["autoResizeDimensions"]
        assert req["dimensions"]["dimension"] == "COLUMNS"
        assert req["dimensions"]["startIndex"] == 2

    def test_autofit_has_no_get_or_del(self):
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("autofit"))
        with pytest.raises(GrammarError, match="is not supported"):
            dispatch("get", c, t, None)
        with pytest.raises(GrammarError, match="is not supported"):
            dispatch("del", c, t, None)


class TestSpreadsheetScalars:
    def _meta(self, properties):
        return {"properties": properties, "sheets": []}

    def test_locale_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("locale"))
        dispatch("put", c, t, "en_GB")
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["locale"] == "en_GB"
        assert req["fields"] == "locale"

    def test_locale_put_rejects_empty(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("locale"))
        with pytest.raises(GrammarError):
            dispatch("put", c, t, "")

    def test_timeZone_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("timeZone"))
        dispatch("put", c, t, "Europe/Berlin")
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["timeZone"] == "Europe/Berlin"
        assert req["fields"] == "timeZone"

    def test_autoRecalc_put_valid(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("autoRecalc"))
        dispatch("put", c, t, "on_change")
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["autoRecalc"] == "ON_CHANGE"

    def test_autoRecalc_put_invalid(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("autoRecalc"))
        with pytest.raises(GrammarError, match="autoRecalc must be"):
            dispatch("put", c, t, "whenever")

    def test_theme_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("theme"))
        body = {"primaryFontFamily": "Roboto"}
        dispatch("put", c, t, body)
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["spreadsheetTheme"] == body
        assert req["fields"] == "spreadsheetTheme"

    def test_theme_get(self):
        theme = {"primaryFontFamily": "Roboto", "themeColors": []}
        c = _client(meta=self._meta({"title": "TB", "spreadsheetTheme": theme}))
        t = Target("SID", None, None, PropertyRef("theme"))
        assert dispatch("get", c, t, None) == theme

    def test_defaultFormat_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("defaultFormat"))
        body = {"backgroundColor": {"red": 1.0}}
        dispatch("put", c, t, body)
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["defaultFormat"] == body
        assert req["fields"] == "defaultFormat"

    def test_iterativeCalc_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("iterativeCalc"))
        body = {"maxIterations": 100, "convergenceThreshold": 0.001}
        dispatch("put", c, t, body)
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["iterativeCalculationSettings"] == body
        assert req["fields"] == "iterativeCalculationSettings"

    def test_theme_put_rejects_non_dict(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("theme"))
        with pytest.raises(GrammarError):
            dispatch("put", c, t, "nope")


class TestRangeNote:
    def test_put_note(self):
        c = _client()
        t = _target(locator="A1", prop_name="note")
        dispatch("put", c, t, "hello")
        req = c.meta_write.call_args[0][1][0]
        assert req["repeatCell"]["cell"]["note"] == "hello"
        assert req["repeatCell"]["fields"] == "note"


# ---------------------------- sheet properties ----------------------------


class TestSheetFreeze:
    def test_put_scalar_rows(self):
        c = _client()
        t = _target(prop_name="freeze")
        dispatch("put", c, t, "3")
        req = c.meta_write.call_args[0][1][0]
        gp = req["updateSheetProperties"]["properties"]["gridProperties"]
        assert gp["frozenRowCount"] == 3 and gp["frozenColumnCount"] == 0

    def test_put_scalar_rows_and_cols(self):
        c = _client()
        t = _target(prop_name="freeze")
        dispatch("put", c, t, "3 1")
        gp = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["gridProperties"]
        assert gp == {"frozenRowCount": 3, "frozenColumnCount": 1}

    def test_put_dict(self):
        c = _client()
        t = _target(prop_name="freeze")
        dispatch("put", c, t, {"rows": 2, "columns": 2})
        gp = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["gridProperties"]
        assert gp == {"frozenRowCount": 2, "frozenColumnCount": 2}

    def test_del_zeros(self):
        c = _client()
        t = _target(prop_name="freeze")
        dispatch("del", c, t, None)
        gp = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["gridProperties"]
        assert gp == {"frozenRowCount": 0, "frozenColumnCount": 0}


class TestSheetColor:
    def test_put_hex(self):
        c = _client()
        t = _target(prop_name="color")
        dispatch("put", c, t, "#ff0000")
        tc = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["tabColor"]
        assert tc["red"] == 1.0
        assert tc.get("green", 0.0) == 0.0

    def test_put_invalid_hex(self):
        c = _client()
        t = _target(prop_name="color")
        with pytest.raises(GrammarError):
            dispatch("put", c, t, "#nothex")

    def test_put_dict_rejects_out_of_range(self):
        """B3 regression: catch the `{"red": 255}` mistake client-side."""
        c = _client()
        t = _target(prop_name="color")
        with pytest.raises(GrammarError, match=r"\[0, 1\]"):
            dispatch("put", c, t, {"red": 255})

    def test_put_dict_accepts_normalized(self):
        c = _client()
        t = _target(prop_name="color")
        dispatch("put", c, t, {"red": 0.5, "green": 0.25})
        tc = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]["tabColor"]
        assert tc == {"red": 0.5, "green": 0.25}


class TestSheetHidden:
    def test_put_true_string(self):
        c = _client()
        t = _target(prop_name="hidden")
        dispatch("put", c, t, "true")
        props = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]
        assert props["hidden"] is True

    def test_put_bool(self):
        c = _client()
        t = _target(prop_name="hidden")
        dispatch("put", c, t, False)
        props = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]
        assert props["hidden"] is False


class TestSheetTitle:
    def test_put_renames(self):
        c = _client()
        t = _target(prop_name="title")
        dispatch("put", c, t, "Renamed")
        props = c.meta_write.call_args[0][1][0]["updateSheetProperties"]["properties"]
        assert props["title"] == "Renamed"

    def test_del_not_supported(self):
        c = _client()
        t = _target(prop_name="title")
        with pytest.raises(GrammarError, match="is not supported"):
            dispatch("del", c, t, None)

    def test_get_returns_server_title_not_lookup_key(self):
        """B7 regression: if the sheet was renamed server-side, reflect that."""
        c = _client(meta={
            "properties": {"title": "Book"},
            "sheets": [{"properties": {"sheetId": 42, "title": "ActualTitle"}}],
        })
        # Target was built using the old name — _sheet_props still finds it
        # by sheetId mismatch won't happen here, but the important contract is
        # that _sheet_title_get reads from props, not from target.sheet.
        t = _target(sheet="ActualTitle", prop_name="title")
        assert dispatch("get", c, t, None) == "ActualTitle"


# ---------------------------- dimension properties ------------------------


class TestDimension:
    def test_height_put(self):
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("height"))
        dispatch("put", c, t, 40)
        req = c.meta_write.call_args[0][1][0]["updateDimensionProperties"]
        assert req["range"]["dimension"] == "ROWS"
        assert req["range"]["startIndex"] == 4 and req["range"]["endIndex"] == 5
        assert req["properties"]["pixelSize"] == 40

    def test_width_put(self):
        c = _client()
        t = Target("SID", "Sheet1", "C", PropertyRef("width"))
        dispatch("put", c, t, 120)
        req = c.meta_write.call_args[0][1][0]["updateDimensionProperties"]
        assert req["range"]["dimension"] == "COLUMNS"
        assert req["range"]["startIndex"] == 2 and req["range"]["endIndex"] == 3

    def test_height_get_reads_from_grid_data(self):
        """B5 regression: meta_read doesn't include rowMetadata; must use grid-data read."""
        c = _client()
        t = Target("SID", "Sheet1", "5", PropertyRef("height"))
        assert dispatch("get", c, t, None) == 25

    def test_width_get_reads_from_grid_data(self):
        c = _client()
        t = Target("SID", "Sheet1", "C", PropertyRef("width"))
        assert dispatch("get", c, t, None) == 120

    def test_dim_get_returns_none_when_no_data(self):
        c = _client(read_reply={
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1"}, "data": []}],
        })
        t = Target("SID", "Sheet1", "5", PropertyRef("height"))
        assert dispatch("get", c, t, None) is None


# ---------------------------- spreadsheet properties ----------------------


class TestSpreadsheetTitle:
    def test_get(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("title"))
        assert dispatch("get", c, t, None) == "TestBook"

    def test_put(self):
        c = _client()
        t = Target("SID", None, None, PropertyRef("title"))
        dispatch("put", c, t, "New Name")
        req = c.meta_write.call_args[0][1][0]["updateSpreadsheetProperties"]
        assert req["properties"]["title"] == "New Name"
        assert req["fields"] == "title"


class TestNamedRanges:
    def test_put_adds_when_missing(self):
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1"}}],
            "namedRanges": [],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "sales"))
        dispatch("put", c, t, "Sheet1!A1:B10")
        req = c.meta_write.call_args[0][1][0]
        assert "addNamedRange" in req
        assert req["addNamedRange"]["namedRange"]["name"] == "sales"
        assert req["addNamedRange"]["namedRange"]["range"]["sheetId"] == 42

    def test_put_updates_when_present(self):
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1"}}],
            "namedRanges": [
                {"namedRangeId": "nr_123", "name": "sales",
                 "range": {"sheetId": 42, "startRowIndex": 0, "endRowIndex": 1}},
            ],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "sales"))
        dispatch("put", c, t, "Sheet1!A1:B10")
        req = c.meta_write.call_args[0][1][0]
        assert "updateNamedRange" in req
        assert req["updateNamedRange"]["namedRange"]["namedRangeId"] == "nr_123"

    def test_del_removes(self):
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1"}}],
            "namedRanges": [
                {"namedRangeId": "nr_123", "name": "sales",
                 "range": {"sheetId": 42}},
            ],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "sales"))
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]
        assert req["deleteNamedRange"]["namedRangeId"] == "nr_123"

    def test_put_quoted_sheet_name_with_embedded_quote(self):
        """B8 regression: 'Bob''s' must unescape to `Bob's` when resolving the sheet."""
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 77, "title": "Bob's"}}],
            "namedRanges": [],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "sales"))
        dispatch("put", c, t, "'Bob''s'!A1:B10")
        req = c.meta_write.call_args[0][1][0]
        assert req["addNamedRange"]["namedRange"]["range"]["sheetId"] == 77

    def test_put_quoted_sheet_name_with_bang_in_name(self):
        """A sheet named with '!' in it is quoted; the first *unquoted* '!' splits."""
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 88, "title": "A!B"}}],
            "namedRanges": [],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "weird"))
        dispatch("put", c, t, "'A!B'!A1")
        req = c.meta_write.call_args[0][1][0]
        assert req["addNamedRange"]["namedRange"]["range"]["sheetId"] == 88

    def test_del_missing_raises(self):
        meta = {
            "properties": {"title": "TB"},
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1"}}],
            "namedRanges": [],
        }
        c = _client(meta=meta)
        t = Target("SID", None, None, PropertyRef("named", "missing"))
        with pytest.raises(GrammarError, match="not found"):
            dispatch("del", c, t, None)


# ---------------------------- parents (Drive folders) --------------------


class TestParents:
    """``.parents`` crosses into the Drive API — verify all four verbs call
    the right SheetsClient helpers with the right folder IDs."""

    def _client_with_parents(self, parents):
        c = _client()
        c.get_parents = MagicMock(return_value=list(parents))
        c.update_parents = MagicMock(return_value={"id": "SID", "parents": list(parents)})
        return c

    def test_get_returns_full_list(self):
        c = self._client_with_parents(["FOLDER_A", "FOLDER_B"])
        t = Target("SID", None, None, PropertyRef("parents"))
        assert dispatch("get", c, t, None) == ["FOLDER_A", "FOLDER_B"]
        c.get_parents.assert_called_once_with("SID")

    def test_get_keyed_returns_folder_if_member(self):
        c = self._client_with_parents(["FOLDER_A"])
        t = Target("SID", None, None, PropertyRef("parents", "FOLDER_A"))
        assert dispatch("get", c, t, None) == "FOLDER_A"

    def test_get_keyed_missing_raises(self):
        c = self._client_with_parents(["FOLDER_A"])
        t = Target("SID", None, None, PropertyRef("parents", "GHOST"))
        with pytest.raises(GrammarError, match="not a parent"):
            dispatch("get", c, t, None)

    def test_put_string_replaces_all_parents(self):
        """`put .parents FID` is a move: new folder added, old folders removed."""
        c = self._client_with_parents(["OLD_A", "OLD_B"])
        t = Target("SID", None, None, PropertyRef("parents"))
        dispatch("put", c, t, "NEW")
        c.update_parents.assert_called_once_with("SID", add=["NEW"], remove=["OLD_A", "OLD_B"])

    def test_put_list_replaces_parent_set(self):
        c = self._client_with_parents(["KEEP", "DROP"])
        t = Target("SID", None, None, PropertyRef("parents"))
        dispatch("put", c, t, ["KEEP", "NEW"])
        # Only the diff is sent — KEEP already in place, DROP removed, NEW added.
        c.update_parents.assert_called_once_with("SID", add=["NEW"], remove=["DROP"])

    def test_put_empty_list_rejected(self):
        """Replacing with nothing would orphan the file — require explicit intent."""
        c = self._client_with_parents(["A"])
        t = Target("SID", None, None, PropertyRef("parents"))
        with pytest.raises(GrammarError, match="at least one"):
            dispatch("put", c, t, [])
        c.update_parents.assert_not_called()

    def test_put_invalid_type_raises(self):
        c = self._client_with_parents(["A"])
        t = Target("SID", None, None, PropertyRef("parents"))
        with pytest.raises(GrammarError, match="folder ID"):
            dispatch("put", c, t, 42)

    def test_new_adds_without_touching_existing(self):
        c = self._client_with_parents(["EXISTING"])
        t = Target("SID", None, None, PropertyRef("parents"))
        dispatch("new", c, t, "ADDED")
        c.update_parents.assert_called_once_with("SID", add=["ADDED"])
        # Must NOT consult get_parents — add is purely additive.
        c.get_parents.assert_not_called()

    def test_new_list_adds_multiple(self):
        c = self._client_with_parents([])
        t = Target("SID", None, None, PropertyRef("parents"))
        dispatch("new", c, t, ["A", "B"])
        c.update_parents.assert_called_once_with("SID", add=["A", "B"])

    def test_del_keyed_removes_one(self):
        c = self._client_with_parents(["KEEP", "REMOVE"])
        t = Target("SID", None, None, PropertyRef("parents", "REMOVE"))
        dispatch("del", c, t, None)
        c.update_parents.assert_called_once_with("SID", remove=["REMOVE"])

    def test_del_keyed_missing_raises(self):
        c = self._client_with_parents(["KEEP"])
        t = Target("SID", None, None, PropertyRef("parents", "GHOST"))
        with pytest.raises(GrammarError, match="not a parent"):
            dispatch("del", c, t, None)
        c.update_parents.assert_not_called()

    def test_del_unkeyed_refuses_orphan(self):
        """Removing all parents leaves the file orphaned — require a folder ID."""
        c = self._client_with_parents(["A", "B"])
        t = Target("SID", None, None, PropertyRef("parents"))
        with pytest.raises(GrammarError, match="would orphan"):
            dispatch("del", c, t, None)
        c.update_parents.assert_not_called()

    def test_supported_includes_parents(self):
        assert "parents" in supported(TargetType.SPREADSHEET)


# ---------------------------- conditional rules ---------------------------


class TestConditional:
    def _meta(self, rules=()):
        return {
            "properties": {"title": "TB"},
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "conditionalFormats": list(rules),
            }],
        }

    def test_get_all(self):
        rules = [{"ranges": [{"sheetId": 42}], "booleanRule": {}}]
        c = _client(meta=self._meta(rules=rules))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional"))
        assert dispatch("get", c, t, None) == rules

    def test_get_by_index(self):
        rules = [{"ranges": [{"sheetId": 42}], "booleanRule": {"a": 1}}]
        c = _client(meta=self._meta(rules=rules))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional", "0"))
        assert dispatch("get", c, t, None) == rules[0]

    def test_new_appends(self):
        c = _client(meta=self._meta(rules=[{"a": 1}]))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional"))
        dispatch("new", c, t, {"booleanRule": {}})
        req = c.meta_write.call_args[0][1][0]["addConditionalFormatRule"]
        assert req["index"] == 1
        assert req["rule"]["ranges"] == [{"sheetId": 42}]

    def test_put_by_index_updates(self):
        c = _client(meta=self._meta(rules=[{"a": 1}, {"b": 2}]))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional", "1"))
        dispatch("put", c, t, {"booleanRule": {}})
        req = c.meta_write.call_args[0][1][0]
        assert "updateConditionalFormatRule" in req
        assert req["updateConditionalFormatRule"]["index"] == 1

    def test_put_out_of_bounds_raises(self):
        """B4 regression: keyed put is an update; index must reference an existing rule."""
        c = _client(meta=self._meta(rules=[{"a": 1}]))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional", "99"))
        with pytest.raises(GrammarError, match="out of range"):
            dispatch("put", c, t, {"booleanRule": {}})

    def test_del_by_index(self):
        c = _client(meta=self._meta(rules=[{"a": 1}, {"b": 2}]))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional", "1"))
        dispatch("del", c, t, None)
        req = c.meta_write.call_args[0][1][0]["deleteConditionalFormatRule"]
        assert req["sheetId"] == 42 and req["index"] == 1

    def test_del_all_reverse_order(self):
        c = _client(meta=self._meta(rules=[{"a": 1}, {"b": 2}, {"c": 3}]))
        t = Target("SID", "Sheet1", None, PropertyRef("conditional"))
        dispatch("del", c, t, None)
        requests = c.meta_write.call_args[0][1]
        indices = [r["deleteConditionalFormatRule"]["index"] for r in requests]
        assert indices == [2, 1, 0]


# ---------------------------- verb wiring --------------------------------


class TestVerbWiring:
    def test_do_get_routes_to_dispatch(self):
        """verbs.do_get must delegate when target.property is set."""
        from sheet_cli.verbs import do_get
        c = _client()
        t = _target(prop_name="freeze")
        result = do_get(c, t)
        assert result == {"rows": 0, "columns": 0}

    def test_do_put_routes_to_dispatch(self):
        from sheet_cli.verbs import do_put
        c = _client()
        t = _target(prop_name="title")
        do_put(c, t, "Hello")
        req = c.meta_write.call_args[0][1][0]
        assert "updateSheetProperties" in req

    def test_do_del_routes_to_dispatch(self):
        from sheet_cli.verbs import do_del
        c = _client()
        t = _target(prop_name="freeze")
        do_del(c, t)
        assert c.meta_write.called

    def test_do_new_routes_to_dispatch(self):
        from sheet_cli.verbs import do_new
        c = _client(meta={
            "properties": {"title": "TB"},
            "sheets": [{
                "properties": {"sheetId": 42, "title": "Sheet1"},
                "conditionalFormats": [],
            }],
        })
        t = Target("SID", "Sheet1", None, PropertyRef("conditional"))
        do_new(c, t, side=None, data={"booleanRule": {}})
        assert "addConditionalFormatRule" in c.meta_write.call_args[0][1][0]

    def test_do_new_rejects_stray_data_on_non_property_target(self):
        """new without a property has no use for a body — refuse rather than drop it silently."""
        from sheet_cli.verbs import do_new
        c = _client()
        t = Target("SID", "Sheet1", None, None)  # plain sheet, no property
        with pytest.raises(GrammarError, match="does not accept a stdin body"):
            do_new(c, t, side=None, data={"something": "ignored"})


# ---------------------------- copy/move rejects property ------------------


class TestCopyMoveRejectsProperty:
    def test_copy_rejects_property_source(self):
        from sheet_cli.dispatch import do_copy
        c = _client()
        src = _target(locator="A1:B2", prop_name="format")
        dst = _target(locator="D1:E2")
        with pytest.raises(GrammarError, match="does not support .property"):
            do_copy(c, src, dst)

    def test_move_rejects_property_dest(self):
        from sheet_cli.dispatch import do_move
        c = _client()
        src = _target(locator="A1:B2")
        dst = _target(locator="D1:E2", prop_name="format")
        with pytest.raises(GrammarError, match="does not support .property"):
            do_move(c, src, dst)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
