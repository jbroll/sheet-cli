"""Unit tests for the batch verb's pure core."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import batch
from sheet_cli.grammar import GrammarError


def _resolver(mapping):
    return lambda title: mapping[title]


def test_values_op():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}],
        _resolver({"Sheet1": 0}),
    )
    assert plan.values == [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}]
    assert plan.clears == []
    assert plan.requests == []


def test_format_op_builds_repeat_cell_with_sheet_id():
    plan = batch.build_batch(
        [{"range": "Sheet1!B6:B10",
          "format": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}}],
        _resolver({"Sheet1": 42}),
    )
    rc = plan.requests[0]["repeatCell"]
    assert rc["range"]["sheetId"] == 42
    assert rc["range"]["startRowIndex"] == 5
    assert rc["range"]["endRowIndex"] == 10
    assert rc["fields"] == (
        "userEnteredFormat.numberFormat.type,userEnteredFormat.numberFormat.pattern"
    )


def test_width_op_requires_and_uses_column_locator():
    plan = batch.build_batch([{"column": "Sheet1!A", "width": 220}], _resolver({"Sheet1": 0}))
    upd = plan.requests[0]["updateDimensionProperties"]
    assert upd["range"] == {
        "sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1
    }
    assert upd["properties"] == {"pixelSize": 220}


def test_height_op_uses_row_locator():
    plan = batch.build_batch([{"row": "Sheet1!5", "height": 30}], _resolver({"Sheet1": 7}))
    upd = plan.requests[0]["updateDimensionProperties"]
    assert upd["range"] == {
        "sheetId": 7, "dimension": "ROWS", "startIndex": 4, "endIndex": 5
    }


def test_multi_action_op_splits_values_and_requests():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1", "values": [["x"]],
          "format": {"textFormat": {"bold": True}}}],
        _resolver({"Sheet1": 0}),
    )
    assert plan.values == [{"range": "Sheet1!A1", "values": [["x"]]}]
    assert plan.requests[0]["repeatCell"]["cell"] == {
        "userEnteredFormat": {"textFormat": {"bold": True}}
    }


def test_clear_op():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1:Z9", "clear": True}], _resolver({"Sheet1": 0})
    )
    assert plan.clears == ["Sheet1!A1:Z9"]
    assert plan.values == []
    assert plan.requests == []


def test_sheet_id_resolved_once_per_sheet():
    calls = []

    def resolver(title):
        calls.append(title)
        return 0

    batch.build_batch(
        [
            {"range": "S!A1", "format": {"textFormat": {"bold": True}}},
            {"range": "S!B1", "format": {"textFormat": {"italic": True}}},
        ],
        resolver,
    )
    assert calls == ["S"]


def test_non_list_payload_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch({"range": "S!A1"}, _resolver({}))


def test_op_without_action_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "S!A1"}], _resolver({}))


def test_op_without_locator_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"values": [[1]]}], _resolver({}))


def test_locator_without_sheet_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "A1", "values": [[1]]}], _resolver({}))


def test_width_on_range_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "S!A1", "width": 5}], _resolver({"S": 0}))
