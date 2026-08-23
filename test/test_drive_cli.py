"""Tests for drive_cli.cli — argparse routing and delegation to ops.

Patch argv / stdout / drive_cli.cli.SheetsClient, invoke main().
"""

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from drive_cli import cli


@pytest.fixture
def fake_client():
    c = MagicMock()
    c.get_file_mime.return_value = "application/pdf"
    c.copy_file.return_value = {"id": "NEW", "url": "u"}
    c.copy_folder.return_value = {"id": "NEW", "copied_files": 0}
    c.copy_spreadsheet.return_value = {"spreadsheetId": "NEW"}
    c.create_folder.return_value = {"id": "F", "url": "u"}
    c.create.return_value = {"spreadsheetId": "S"}
    c.update_parents.return_value = {"id": "ID"}
    c.get_parents.return_value = ["P1"]
    c.list_files.return_value = [{"id": "a", "name": "x", "mimeType": "application/pdf"}]
    return c


def run_cli(argv, fake_client):
    out, err = io.StringIO(), io.StringIO()
    code = None
    with patch.object(sys, "argv", ["drive-cli"] + argv), \
         patch.object(sys, "stdout", out), \
         patch.object(sys, "stderr", err), \
         patch("drive_cli.cli.SheetsClient", return_value=fake_client):
        try:
            cli.main()
        except SystemExit as e:
            code = e.code
    return out.getvalue(), err.getvalue(), code


class TestCopy:
    def test_copy_file_into_folder_with_name(self, fake_client):
        _, _, code = run_cli(["copy", "FILE1", "FOLDER9", "--name", "New"], fake_client)
        assert code in (None, 0)
        fake_client.copy_file.assert_called_once_with(
            "FILE1", new_title="New", parent_folder_id="FOLDER9")

    def test_copy_file_no_folder(self, fake_client):
        run_cli(["copy", "FILE1"], fake_client)
        fake_client.copy_file.assert_called_once_with(
            "FILE1", new_title=None, parent_folder_id=None)

    def test_copy_folder_recurses(self, fake_client):
        fake_client.get_file_mime.return_value = "application/vnd.google-apps.folder"
        run_cli(["copy", "FOLDER1", "DEST"], fake_client)
        fake_client.copy_folder.assert_called_once_with(
            "FOLDER1", new_title=None, parent_folder_id="DEST")


class TestNew:
    def test_new_folder_with_parent(self, fake_client):
        run_cli(["new", "folder", "Docs", "PARENT"], fake_client)
        fake_client.create_folder.assert_called_once_with("Docs", parent_folder_id="PARENT")

    def test_new_sheet_no_parent(self, fake_client):
        run_cli(["new", "sheet", "Budget"], fake_client)
        fake_client.create.assert_called_once_with("Budget", parent_folder_id=None)


class TestMove:
    def test_move_relocate(self, fake_client):
        run_cli(["move", "ID", "DEST"], fake_client)
        fake_client.update_parents.assert_called_once_with(
            "ID", add=["DEST"], remove=["P1"])

    def test_move_add(self, fake_client):
        run_cli(["move", "ID", "DEST", "--add"], fake_client)
        fake_client.update_parents.assert_called_once_with("ID", add=["DEST"])


class TestListParents:
    def test_list_root(self, fake_client):
        stdout, _, code = run_cli(["list"], fake_client)
        fake_client.list_files.assert_called_once_with(folder_id=None)
        assert "a" in stdout

    def test_list_folder(self, fake_client):
        run_cli(["list", "FOLDER1"], fake_client)
        fake_client.list_files.assert_called_once_with(folder_id="FOLDER1")

    def test_parents(self, fake_client):
        stdout, _, _ = run_cli(["parents", "ID"], fake_client)
        fake_client.get_parents.assert_called_once_with("ID")
        assert "P1" in stdout


class TestErrors:
    def test_unknown_verb_errors(self, fake_client):
        _, _, code = run_cli(["frobnicate", "x"], fake_client)
        assert code == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestTransferCommands:
    """inventory / chown / accept routing, with a manifest on disk."""

    @pytest.fixture
    def transfer_client(self, fake_client):
        fake_client.whoami.return_value = {"emailAddress": "alice@example.com"}
        fake_client.walk_tree.return_value = [{
            "id": "A", "name": "a", "mimeType": "application/pdf", "parents": ["ROOT"],
            "owner": "alice@example.com", "depth": 0, "is_folder": False,
            "shortcut_target": None, "shared_drive": False, "can_share": True}]
        return fake_client

    def _manifest(self, tmp_path, transfer_client):
        path = str(tmp_path / "m.json")
        run_cli(["inventory", "ROOT", "-o", path], transfer_client)
        return path

    def test_inventory_writes_a_manifest(self, tmp_path, transfer_client):
        path = str(tmp_path / "m.json")
        out, _, code = run_cli(["inventory", "ROOT", "-o", path], transfer_client)
        assert code in (None, 0)
        transfer_client.walk_tree.assert_called_once_with("ROOT")
        assert json.loads(open(path).read())["nodes"][0]["id"] == "A"
        assert json.loads(out)["nodes"] == 1

    def test_inventory_defaults_to_stdout(self, transfer_client):
        out, _, code = run_cli(["inventory", "ROOT"], transfer_client)
        assert code in (None, 0)
        assert json.loads(out)["nodes"][0]["id"] == "A"

    def test_chown_transfers_and_updates_the_manifest(self, tmp_path, transfer_client):
        path = self._manifest(tmp_path, transfer_client)
        out, _, code = run_cli(
            ["chown", path, "--to", "bob@example.com", "--from", "alice@example.com",
             "--mode", "direct", "--as", "alice@example.com"], transfer_client)
        assert code in (None, 0)
        transfer_client.transfer_ownership.assert_called_once_with("A", "bob@example.com")
        assert json.loads(open(path).read())["nodes"][0]["transfer"]["state"] == "owned"
        assert json.loads(out)["counts"] == {"owned": 1}

    def test_chown_dry_run_leaves_the_manifest_alone(self, tmp_path, transfer_client):
        path = self._manifest(tmp_path, transfer_client)
        before = open(path).read()
        _, _, code = run_cli(["chown", path, "--to", "bob@example.com", "--dry-run"],
                             transfer_client)
        assert code in (None, 0)
        transfer_client.transfer_ownership.assert_not_called()
        assert open(path).read() == before

    def test_accept_reads_pending_state_from_the_manifest(self, tmp_path, transfer_client):
        path = self._manifest(tmp_path, transfer_client)
        run_cli(["chown", path, "--to", "bob@example.com", "--mode", "pending",
                 "--as", "alice@example.com"], transfer_client)
        _, _, code = run_cli(["accept", path, "--as", "bob@example.com"], transfer_client)
        assert code in (None, 0)
        transfer_client.accept_ownership.assert_called_once_with("A", "bob@example.com")
        assert json.loads(open(path).read())["nodes"][0]["transfer"]["state"] == "owned"

    def test_verbose_includes_per_node_results(self, tmp_path, transfer_client):
        path = self._manifest(tmp_path, transfer_client)
        out, _, _ = run_cli(["chown", path, "--to", "bob@example.com", "--verbose"],
                            transfer_client)
        assert json.loads(out)["results"][0]["id"] == "A"

    def test_plan_walks_and_reports_owners_as_text(self, transfer_client):
        out, _, code = run_cli(
            ["plan", "ROOT", "--to", "bob@example.com"], transfer_client)
        assert code in (None, 0)
        transfer_client.walk_tree.assert_called_once_with("ROOT")
        assert "alice@example.com" in out
        assert "1 items" in out
        assert "drive-cli chown" in out

    def test_plan_json_format(self, transfer_client):
        out, _, code = run_cli(
            ["plan", "ROOT", "--to", "bob@example.com", "--format", "json"],
            transfer_client)
        assert code in (None, 0)
        assert json.loads(out)["owners"][0]["email"] == "alice@example.com"

    def test_plan_saves_a_manifest_for_the_chown_pass(self, tmp_path, transfer_client):
        path = str(tmp_path / "m.json")
        out, _, _ = run_cli(
            ["plan", "ROOT", "--to", "bob@example.com", "-o", path], transfer_client)
        assert json.loads(open(path).read())["nodes"][0]["id"] == "A"
        assert path in out

    def test_plan_reuses_a_manifest_instead_of_walking(self, tmp_path, transfer_client):
        path = self._manifest(tmp_path, transfer_client)
        transfer_client.walk_tree.reset_mock()
        out, _, code = run_cli(
            ["plan", "-m", path, "--to", "bob@example.com"], transfer_client)
        assert code in (None, 0)
        transfer_client.walk_tree.assert_not_called()
        assert path in out

    def test_plan_names_accounts_that_still_need_a_login(self, transfer_client):
        with patch("drive_cli.cli.cached_accounts", return_value=set()):
            out, _, _ = run_cli(["plan", "ROOT", "--to", "bob@example.com"],
                                transfer_client)
        assert "NEEDS LOGIN" in out
        assert "drive-cli auth --as=alice@example.com" in out

    def test_account_selects_a_per_account_token(self, transfer_client):
        with patch("drive_cli.cli.SheetsClient", return_value=transfer_client) as ctor, \
             patch.object(sys, "argv", ["drive-cli", "list", "--as", "bob@example.com"]), \
             patch.object(sys, "stdout", io.StringIO()):
            cli.main()
        assert ctor.call_args.kwargs["token_path"].endswith("token-bob@example.com.json")
