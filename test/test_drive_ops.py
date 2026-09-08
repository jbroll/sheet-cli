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


# -------------------------------- do_upload --------------------------------

DOC_MIME = "application/vnd.google-apps.document"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def docx(tmp_path):
    path = tmp_path / "flyer.docx"
    path.write_bytes(b"bytes")
    return str(path)


class TestDoUpload:
    def _uploaded(self, client, **over):
        result = {"id": "NEW", "name": "flyer", "mimeType": DOC_MIME,
                  "webViewLink": "https://docs.google.com/document/d/NEW",
                  "parents": []}
        result.update(over)
        client.upload_file.return_value = result
        client.update_file_content.return_value = result
        return result

    def test_no_target_creates_at_root_converting(self, client, docx):
        self._uploaded(client)
        result = ops.do_upload(client, docx)
        client.get_file_mime.assert_not_called()
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer", convert_to=DOC_MIME,
            parent_folder_id=None)
        assert result["action"] == "created"
        assert result["id"] == "NEW"

    def test_folder_target_creates_inside_it(self, client, docx):
        self._uploaded(client)
        client.get_file_mime.return_value = FOLDER_MIME
        ops.do_upload(client, docx, "FOLDER1")
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer", convert_to=DOC_MIME,
            parent_folder_id="FOLDER1")

    def test_file_target_replaces_its_content(self, client, docx):
        self._uploaded(client, id="DOC1")
        client.get_file_mime.return_value = DOC_MIME
        result = ops.do_upload(client, docx, "DOC1")
        client.update_file_content.assert_called_once_with(
            "DOC1", docx, DOCX, name=None)
        client.upload_file.assert_not_called()
        assert result["action"] == "replaced"
        assert result["id"] == "DOC1"

    def test_raw_skips_conversion_and_keeps_the_extension_in_the_name(
            self, client, docx):
        self._uploaded(client)
        ops.do_upload(client, docx, raw=True)
        client.upload_file.assert_called_once_with(
            docx, DOCX, name="flyer.docx", convert_to=None,
            parent_folder_id=None)

    def test_to_forces_a_native_type(self, client, tmp_path):
        self._uploaded(client)
        path = str(tmp_path / "notes.txt")
        open(path, "w").write("hi")
        ops.do_upload(client, path, to="doc")
        client.upload_file.assert_called_once_with(
            path, "text/plain", name="notes", convert_to=DOC_MIME,
            parent_folder_id=None)

    def test_explicit_name_wins(self, client, docx):
        self._uploaded(client)
        ops.do_upload(client, docx, name="Q3 Flyer")
        assert client.upload_file.call_args[1]["name"] == "Q3 Flyer"

    def test_mime_overrides_the_extension_guess(self, client, tmp_path):
        self._uploaded(client)
        path = str(tmp_path / "data")
        open(path, "w").write("a,b")
        ops.do_upload(client, path, mime="text/csv")
        assert client.upload_file.call_args[0][1] == "text/csv"
        assert client.upload_file.call_args[1]["convert_to"] == \
            "application/vnd.google-apps.spreadsheet"

    def test_unknown_extension_without_mime_raises(self, client, tmp_path):
        path = str(tmp_path / "data")
        open(path, "w").write("x")
        with pytest.raises(ValueError, match="--mime"):
            ops.do_upload(client, path)

    def test_missing_file_raises(self, client, tmp_path):
        with pytest.raises(ValueError, match="no such file"):
            ops.do_upload(client, str(tmp_path / "absent.docx"))

    def test_raw_with_to_raises(self, client, docx):
        with pytest.raises(ValueError, match="mutually exclusive"):
            ops.do_upload(client, docx, raw=True, to="doc")

    def test_unknown_to_raises(self, client, docx):
        with pytest.raises(ValueError, match="doc, sheet, or slides"):
            ops.do_upload(client, docx, to="banana")

    def test_to_disagreeing_with_the_replaced_file_raises(self, client, docx):
        client.get_file_mime.return_value = \
            "application/vnd.google-apps.spreadsheet"
        with pytest.raises(ValueError, match="spreadsheet"):
            ops.do_upload(client, docx, "SHEET1", to="doc")
        client.update_file_content.assert_not_called()

    def test_to_matching_the_replaced_file_is_fine(self, client, docx):
        self._uploaded(client, id="DOC1")
        client.get_file_mime.return_value = DOC_MIME
        assert ops.do_upload(client, docx, "DOC1", to="doc")["action"] == "replaced"

    def test_raw_source_with_no_native_equivalent_uploads_as_is(
            self, client, tmp_path):
        self._uploaded(client, mimeType="application/pdf")
        path = str(tmp_path / "scan.pdf")
        open(path, "wb").write(b"%PDF")
        ops.do_upload(client, path)
        client.upload_file.assert_called_once_with(
            path, "application/pdf", name="scan.pdf", convert_to=None,
            parent_folder_id=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
