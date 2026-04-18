"""Tests for verbs (do_get, do_put, do_del, do_new).

The verbs module dispatches on TargetType and delegates to a SheetsClient.
We mock the client and assert the right methods are called with the right args.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli.grammar import GrammarError, Target
from sheet_cli.verbs import do_del, do_get, do_new, do_put


@pytest.fixture
def client():
    c = MagicMock()
    # Default meta_read response: one sheet "Sheet1" with sheetId 0
    c.meta_read.return_value = {
        "sheets": [
            {"properties": {"title": "Sheet1", "sheetId": 0}},
            {"properties": {"title": "Sheet2", "sheetId": 123}},
        ]
    }
    return c


# =============================== do_get ===================================


class TestDoGet:
    def test_drive_calls_list_spreadsheets(self, client):
        client.list_spreadsheets.return_value = [{"id": "a"}]
        result = do_get(client, Target(None, None, None))
        client.list_spreadsheets.assert_called_once()
        assert result == [{"id": "a"}]

    def test_spreadsheet_calls_meta_read(self, client):
        do_get(client, Target("SID", None, None))
        client.meta_read.assert_called_once_with("SID")

    def test_sheet_calls_read_with_sheet_name(self, client):
        do_get(client, Target("SID", "Sheet1", None))
        args, kwargs = client.read.call_args
        assert args[0] == "SID"
        assert args[1] == ["Sheet1"]

    def test_range_calls_read_with_a1(self, client):
        do_get(client, Target("SID", "Sheet1", "A1:B10"))
        args, _ = client.read.call_args
        assert args[0] == "SID"
        assert args[1] == ["Sheet1!A1:B10"]

    def test_row_calls_read_with_row_locator(self, client):
        do_get(client, Target("SID", "Sheet1", "5"))
        args, _ = client.read.call_args
        assert args[1] == ["Sheet1!5"]

    def test_column_calls_read_with_col_locator(self, client):
        do_get(client, Target("SID", "Sheet1", "C"))
        args, _ = client.read.call_args
        assert args[1] == ["Sheet1!C"]


# =============================== do_put ===================================


class TestDoPut:
    def test_scalar_single_cell(self, client):
        do_put(client, Target("SID", "Sheet1", "A1"), "hello")
        args, _ = client.write.call_args
        assert args[0] == "SID"
        assert args[1] == [{"range": "Sheet1!A1", "values": [["hello"]]}]

    def test_dict_cell_keys_qualify_with_target_sheet(self, client):
        do_put(client, Target("SID", "Sheet1", None), {"A1": "hi", "B2": 42})
        _, _ = client.write.call_args
        ops = client.write.call_args.args[1]
        ranges = {op["range"] for op in ops}
        assert ranges == {"Sheet1!A1", "Sheet1!B2"}
        values = {op["range"]: op["values"] for op in ops}
        assert values["Sheet1!A1"] == [["hi"]]
        assert values["Sheet1!B2"] == [[42]]

    def test_dict_range_keys_with_2d_values(self, client):
        data = {"A1:B2": [[1, 2], [3, 4]]}
        do_put(client, Target("SID", "Sheet1", None), data)
        ops = client.write.call_args.args[1]
        assert ops == [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}]

    def test_dict_key_with_bang_passes_through(self, client):
        do_put(client, Target("SID", "Sheet1", None), {"Sheet2!A1": "x"})
        ops = client.write.call_args.args[1]
        assert ops == [{"range": "Sheet2!A1", "values": [["x"]]}]

    def test_bare_2d_array(self, client):
        do_put(client, Target("SID", "Sheet1", "A1:B2"), [[1, 2], [3, 4]])
        ops = client.write.call_args.args[1]
        assert ops == [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}]

    def test_drive_target_rejected(self, client):
        with pytest.raises(GrammarError):
            do_put(client, Target(None, None, None), {"A1": 1})

    def test_spreadsheet_target_rejected(self, client):
        with pytest.raises(GrammarError):
            do_put(client, Target("SID", None, None), {"A1": 1})


# =============================== do_del ===================================


class TestDoDel:
    def test_drive_refused(self, client):
        with pytest.raises(GrammarError):
            do_del(client, Target(None, None, None))

    def test_spreadsheet_deletes_via_drive(self, client):
        do_del(client, Target("SID", None, None))
        client.delete_spreadsheet.assert_called_once_with("SID")

    def test_sheet_issues_deleteSheet_request(self, client):
        do_del(client, Target("SID", "Sheet2", None))
        args, _ = client.meta_write.call_args
        assert args[0] == "SID"
        assert args[1] == [{"deleteSheet": {"sheetId": 123}}]

    def test_range_calls_clear(self, client):
        do_del(client, Target("SID", "Sheet1", "A1:B10"))
        client.clear.assert_called_once_with("SID", ["Sheet1!A1:B10"])

    def test_row_issues_deleteDimension(self, client):
        do_del(client, Target("SID", "Sheet1", "5"))
        requests = client.meta_write.call_args.args[1]
        assert requests == [{
            "deleteDimension": {
                "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": 4, "endIndex": 5}
            }
        }]

    def test_column_issues_deleteDimension(self, client):
        do_del(client, Target("SID", "Sheet1", "C"))
        requests = client.meta_write.call_args.args[1]
        assert requests == [{
            "deleteDimension": {
                "range": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3}
            }
        }]


# =============================== do_new ===================================


class TestDoNew:
    def test_drive_creates_untitled(self, client):
        do_new(client, Target(None, None, None))
        client.create.assert_called_once_with("Untitled spreadsheet")

    def test_spreadsheet_treats_sid_as_title(self, client):
        do_new(client, Target("My Title", None, None))
        client.create.assert_called_once_with("My Title")

    def test_sheet_issues_addSheet(self, client):
        do_new(client, Target("SID", "NewSheet", None))
        requests = client.meta_write.call_args.args[1]
        assert requests == [{"addSheet": {"properties": {"title": "NewSheet"}}}]

    def test_row_default_side_below(self, client):
        do_new(client, Target("SID", "Sheet1", "5"))
        req = client.meta_write.call_args.args[1][0]
        # "below" == after == start shifts from 4 to 5
        assert req["insertDimension"]["range"]["startIndex"] == 5
        assert req["insertDimension"]["inheritFromBefore"] is True

    def test_row_above_side(self, client):
        do_new(client, Target("SID", "Sheet1", "5"), side="above")
        req = client.meta_write.call_args.args[1][0]
        assert req["insertDimension"]["range"]["startIndex"] == 4
        assert req["insertDimension"]["inheritFromBefore"] is False

    def test_column_default_side_right(self, client):
        do_new(client, Target("SID", "Sheet1", "C"))
        req = client.meta_write.call_args.args[1][0]
        # right == after; C is index 2, so startIndex 3
        assert req["insertDimension"]["range"]["startIndex"] == 3
        assert req["insertDimension"]["inheritFromBefore"] is True

    def test_column_left_side(self, client):
        do_new(client, Target("SID", "Sheet1", "C"), side="left")
        req = client.meta_write.call_args.args[1][0]
        assert req["insertDimension"]["range"]["startIndex"] == 2
        assert req["insertDimension"]["inheritFromBefore"] is False

    def test_row_with_bad_side_raises(self, client):
        with pytest.raises(GrammarError):
            do_new(client, Target("SID", "Sheet1", "5"), side="left")

    def test_column_with_bad_side_raises(self, client):
        with pytest.raises(GrammarError):
            do_new(client, Target("SID", "Sheet1", "C"), side="above")

    def test_range_not_valid_for_new(self, client):
        with pytest.raises(GrammarError):
            do_new(client, Target("SID", "Sheet1", "A1:B2"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
