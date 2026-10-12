"""Unit tests for the shared batchUpdate request builders."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import builders


def test_fields_mask_walks_to_leaves():
    mask = builders.fields_mask(
        {"textFormat": {"bold": True}, "backgroundColor": {"red": 1.0}},
        prefix="userEnteredFormat.",
    )
    assert set(mask.split(",")) == {
        "userEnteredFormat.textFormat.bold",
        "userEnteredFormat.backgroundColor.red",
    }


def test_format_request_sets_fields_mask():
    req = builders.format_request(
        {"sheetId": 3}, {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}
    )
    rc = req["repeatCell"]
    assert rc["range"] == {"sheetId": 3}
    assert rc["cell"] == {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}}
    assert rc["fields"] == (
        "userEnteredFormat.numberFormat.type,userEnteredFormat.numberFormat.pattern"
    )


def test_note_request_uses_note_field():
    req = builders.note_request({"sheetId": 0}, "hello")
    assert req["repeatCell"]["cell"] == {"note": "hello"}
    assert req["repeatCell"]["fields"] == "note"


def test_borders_request_merges_range():
    req = builders.borders_request({"sheetId": 0}, {"top": {"style": "SOLID"}})
    assert req["updateBorders"] == {"range": {"sheetId": 0}, "top": {"style": "SOLID"}}


def test_validation_request():
    rule = {"condition": {"type": "NUMBER_GREATER"}}
    req = builders.validation_request({"sheetId": 0}, rule)
    assert req["setDataValidation"] == {"range": {"sheetId": 0}, "rule": rule}


def test_merge_request():
    req = builders.merge_request({"sheetId": 0}, "MERGE_ALL")
    assert req["mergeCells"] == {"range": {"sheetId": 0}, "mergeType": "MERGE_ALL"}


def test_dimension_request_coerces_pixels_to_int():
    req = builders.dimension_request({"sheetId": 0}, "220")
    upd = req["updateDimensionProperties"]
    assert upd["properties"] == {"pixelSize": 220}
    assert upd["fields"] == "pixelSize"
