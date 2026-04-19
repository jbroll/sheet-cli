"""Tests for dispatch (do_copy, do_move) — server-side optimizations and fallbacks."""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli.dispatch import do_copy, do_move
from sheet_cli.grammar import GrammarError, Target


@pytest.fixture
def client():
    c = MagicMock()
    # Default meta_read: Sheet1→0, Sheet2→123
    c.meta_read.return_value = {
        "sheets": [
            {"properties": {"title": "Sheet1", "sheetId": 0}},
            {"properties": {"title": "Sheet2", "sheetId": 123}},
        ]
    }
    return c


# =============================== do_copy ==================================


class TestDoCopy:
    def test_cross_spreadsheet_whole_sheet_uses_copyTo(self, client):
        src = Target("SID1", "Sheet1", None)
        dst = Target("SID2", None, None)
        do_copy(client, src, dst)
        client.copy_sheet_to.assert_called_once_with("SID1", 0, "SID2")
        # Must NOT read/write (server-side)
        client.read.assert_not_called()
        client.write.assert_not_called()

    def test_whole_spreadsheet_copy_uses_drive_files_copy(self, client):
        """SPREADSHEET → SPREADSHEET (dest SID slot is a title) triggers Drive files.copy."""
        src = Target("SID1", None, None)
        dst = Target("New Title", None, None)
        client.copy_spreadsheet.return_value = {
            "spreadsheetId": "NEW_SID",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/NEW_SID",
            "name": "New Title",
            "parents": [],
        }
        result = do_copy(client, src, dst)
        client.copy_spreadsheet.assert_called_once_with("SID1", new_title="New Title")
        # Must NOT fall into sheet-level paths.
        client.copy_sheet_to.assert_not_called()
        client.meta_write.assert_not_called()
        assert result["spreadsheetId"] == "NEW_SID"

    def test_whole_spreadsheet_copy_to_drive_uses_default_title(self, client):
        """SPREADSHEET → DRIVE (bare empty dest) uses Drive's default 'Copy of ...' name."""
        src = Target("SID1", None, None)
        dst = Target(None, None, None)
        client.copy_spreadsheet.return_value = {
            "spreadsheetId": "NEW_SID",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/NEW_SID",
            "name": "Copy of Original",
            "parents": [],
        }
        do_copy(client, src, dst)
        client.copy_spreadsheet.assert_called_once_with("SID1", new_title=None)

    def test_whole_spreadsheet_copy_rejects_self(self, client):
        """Copying a spreadsheet onto its own ID is a no-op aliasing bug — refuse."""
        src = Target("SID1", None, None)
        dst = Target("SID1", None, None)
        with pytest.raises(GrammarError, match="same"):
            do_copy(client, src, dst)
        client.copy_spreadsheet.assert_not_called()

    def test_same_spreadsheet_range_uses_copyPaste(self, client):
        src = Target("SID", "Sheet1", "A1:B2")
        dst = Target("SID", "Sheet2", "D1:E2")
        do_copy(client, src, dst)
        requests = client.meta_write.call_args.args[1]
        assert len(requests) == 1
        cp = requests[0]["copyPaste"]
        assert cp["source"]["sheetId"] == 0
        assert cp["destination"]["sheetId"] == 123
        assert cp["pasteType"] == "PASTE_NORMAL"
        client.read.assert_not_called()
        client.write.assert_not_called()

    def test_cross_spreadsheet_range_uses_read_write_fallback(self, client):
        src = Target("SID1", "Sheet1", "A1:B2")
        dst = Target("SID2", "Sheet1", "D1")
        client.read.return_value = {"values": [[1, 2], [3, 4]]}
        result = do_copy(client, src, dst)
        client.read.assert_called_once()
        client.write.assert_called_once()
        # write should target SID2 and Sheet1!D1
        args, _ = client.write.call_args
        assert args[0] == "SID2"
        assert args[1] == [{"range": "Sheet1!D1", "values": [[1, 2], [3, 4]]}]
        assert result["copied"] == 4

    def test_cross_spreadsheet_range_empty_source(self, client):
        src = Target("SID1", "Sheet1", "A1:B2")
        dst = Target("SID2", "Sheet1", "D1")
        client.read.return_value = {"values": []}
        result = do_copy(client, src, dst)
        client.write.assert_not_called()
        assert result["copied"] == 0

    def test_missing_spreadsheet_id_raises(self, client):
        with pytest.raises(GrammarError):
            do_copy(client, Target(None, None, None), Target("SID", None, None))

    def test_unsupported_shape_raises(self, client):
        # row → column isn't a supported copy shape
        src = Target("SID", "Sheet1", "5")
        dst = Target("SID", "Sheet1", "C")
        with pytest.raises(GrammarError):
            do_copy(client, src, dst)


# =============================== do_move ==================================


class TestDoMove:
    def test_same_sheet_row_move_uses_moveDimension(self, client):
        src = Target("SID", "Sheet1", "5")
        dst = Target("SID", "Sheet1", "2")
        do_move(client, src, dst)
        requests = client.meta_write.call_args.args[1]
        md = requests[0]["moveDimension"]
        assert md["source"]["dimension"] == "ROWS"
        assert md["source"]["startIndex"] == 4
        assert md["source"]["endIndex"] == 5
        assert md["destinationIndex"] == 1

    def test_same_sheet_column_move_uses_moveDimension(self, client):
        src = Target("SID", "Sheet1", "C")
        dst = Target("SID", "Sheet1", "A")
        do_move(client, src, dst)
        md = client.meta_write.call_args.args[1][0]["moveDimension"]
        assert md["source"]["dimension"] == "COLUMNS"
        assert md["source"]["startIndex"] == 2
        assert md["destinationIndex"] == 0

    def test_same_spreadsheet_range_uses_cutPaste(self, client):
        src = Target("SID", "Sheet1", "A1:B2")
        dst = Target("SID", "Sheet2", "D1:E2")
        do_move(client, src, dst)
        requests = client.meta_write.call_args.args[1]
        cp = requests[0]["cutPaste"]
        assert cp["source"]["sheetId"] == 0
        assert cp["destination"]["sheetId"] == 123
        client.read.assert_not_called()
        client.write.assert_not_called()

    def test_cross_spreadsheet_sheet_move_copies_then_deletes(self, client):
        src = Target("SID1", "Sheet1", None)
        dst = Target("SID2", None, None)
        do_move(client, src, dst)
        # Server-side copy + deleteSheet
        client.copy_sheet_to.assert_called_once_with("SID1", 0, "SID2")
        # After the copy, a deleteSheet batch should fire
        delete_calls = [c for c in client.meta_write.call_args_list
                        if c.args[1] == [{"deleteSheet": {"sheetId": 0}}]]
        assert len(delete_calls) == 1

    def test_cross_spreadsheet_range_move_copies_then_clears(self, client):
        src = Target("SID1", "Sheet1", "A1:B2")
        dst = Target("SID2", "Sheet1", "D1")
        client.read.return_value = {"values": [[1, 2], [3, 4]]}
        do_move(client, src, dst)
        client.read.assert_called_once()
        client.write.assert_called_once()
        client.clear.assert_called_once_with("SID1", ["Sheet1!A1:B2"])

    def test_missing_spreadsheet_id_raises(self, client):
        with pytest.raises(GrammarError):
            do_move(client, Target(None, None, None), Target("SID", None, None))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
