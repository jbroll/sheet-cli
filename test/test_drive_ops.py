"""Tests for drive_cli.ops — shared Drive verb core (mocked SheetsClient)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from drive_cli import ops

FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


@pytest.fixture
def client():
    return MagicMock()


# --------------------------------- do_copy ---------------------------------


class TestDoCopy:
    def test_folder_routes_to_copy_folder(self, client):
        client.get_file_mime.return_value = FOLDER_MIME
        client.copy_folder.return_value = {"id": "NEW"}
        ops.do_copy(client, "FOLDER1", folder="DEST", name="X")
        client.copy_folder.assert_called_once_with(
            "FOLDER1", new_title="X", parent_folder_id="DEST")
        client.copy_file.assert_not_called()

    def test_spreadsheet_routes_to_copy_spreadsheet(self, client):
        client.get_file_mime.return_value = SHEET_MIME
        client.copy_spreadsheet.return_value = {"spreadsheetId": "NEW"}
        ops.do_copy(client, "SID1", folder="DEST")
        client.copy_spreadsheet.assert_called_once_with(
            "SID1", new_title=None, parent_folder_id="DEST")

    def test_other_file_routes_to_copy_file(self, client):
        client.get_file_mime.return_value = "application/pdf"
        client.copy_file.return_value = {"id": "NEW"}
        ops.do_copy(client, "PDF1")
        client.copy_file.assert_called_once_with(
            "PDF1", new_title=None, parent_folder_id=None)


# --------------------------------- do_new ----------------------------------


class TestDoNew:
    def test_new_folder(self, client):
        client.create_folder.return_value = {"id": "F"}
        ops.do_new(client, "folder", "Docs", folder="PARENT")
        client.create_folder.assert_called_once_with("Docs", parent_folder_id="PARENT")

    def test_new_sheet(self, client):
        client.create.return_value = {"spreadsheetId": "S"}
        ops.do_new(client, "sheet", "Budget", folder="PARENT")
        client.create.assert_called_once_with("Budget", parent_folder_id="PARENT")

    def test_new_unknown_kind_raises(self, client):
        with pytest.raises(ValueError, match="kind"):
            ops.do_new(client, "banana", "X")


# --------------------------------- do_move ---------------------------------


class TestDoMove:
    def test_move_relocates_replacing_parents(self, client):
        client.get_parents.return_value = ["OLD"]
        client.update_parents.return_value = {"id": "ID"}
        ops.do_move(client, "ID", "DEST")
        client.update_parents.assert_called_once_with(
            "ID", add=["DEST"], remove=["OLD"])

    def test_move_add_keeps_existing_parents(self, client):
        ops.do_move(client, "ID", "DEST", add=True)
        client.update_parents.assert_called_once_with("ID", add=["DEST"])
        client.get_parents.assert_not_called()


# ------------------------------ do_list / parents --------------------------


class TestListAndParents:
    def test_list_root(self, client):
        client.list_files.return_value = [{"id": "a"}]
        result = ops.do_list(client)
        client.list_files.assert_called_once_with(folder_id=None)
        assert result == [{"id": "a"}]

    def test_list_folder(self, client):
        client.list_files.return_value = []
        ops.do_list(client, folder="FOLDER1")
        client.list_files.assert_called_once_with(folder_id="FOLDER1")

    def test_parents(self, client):
        client.get_parents.return_value = ["P1", "P2"]
        assert ops.do_parents(client, "ID") == ["P1", "P2"]
        client.get_parents.assert_called_once_with("ID")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
