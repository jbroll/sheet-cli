"""End-to-end CLI smoke tests for the six-verb v2 CLI.

We mock SheetsClient at the module level, patch sys.argv, and invoke main().
Assertions check that the right client method was called with the right args
and that stdout/stderr output matches the documented rules.
"""

import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import cli


@pytest.fixture
def fake_client():
    c = MagicMock()
    c.meta_read.return_value = {
        "properties": {"title": "Test"},
        "sheets": [
            {"properties": {"title": "Sheet1", "sheetId": 0}},
            {"properties": {"title": "Sheet2", "sheetId": 42}},
        ],
    }
    c.list_spreadsheets.return_value = [{"id": "abc", "name": "x"}]
    c.read.return_value = {"range": "Sheet1!A1", "values": [["hello"]]}
    c.write.return_value = {"totalUpdatedCells": 1}
    c.clear.return_value = {"clearedRanges": ["Sheet1!A1:B2"]}
    c.create.return_value = {"spreadsheetId": "NEW", "spreadsheetUrl": "http://x"}
    c.meta_write.return_value = {"replies": []}
    return c


def run_cli(argv, fake_client, stdin_text=""):
    """Invoke cli.main() with patched argv, SheetsClient, and stdin.

    Returns (stdout, stderr, exit_code_or_None).
    """
    out, err = io.StringIO(), io.StringIO()
    exit_code = None
    with patch.object(sys, "argv", ["sheet-cli"] + argv), \
         patch.object(sys, "stdin", io.StringIO(stdin_text)), \
         patch.object(sys, "stdout", out), \
         patch.object(sys, "stderr", err), \
         patch("sheet_cli.cli.SheetsClient", return_value=fake_client):
        # stdin.isatty() needs to return False for pipe detection
        sys.stdin.isatty = lambda: not stdin_text  # type: ignore[method-assign]
        try:
            cli.main()
        except SystemExit as e:
            exit_code = e.code
    return out.getvalue(), err.getvalue(), exit_code


# ================================ get =====================================


class TestCliGet:
    def test_get_no_target_lists_drive_as_json(self, fake_client):
        stdout, _, code = run_cli(["get"], fake_client)
        fake_client.list_spreadsheets.assert_called_once()
        assert code in (None, 0)
        assert "abc" in stdout

    def test_get_spreadsheet_prints_json(self, fake_client):
        stdout, _, _ = run_cli(["get", "SID"], fake_client)
        fake_client.meta_read.assert_called_with("SID")
        assert "Test" in stdout

    def test_get_range_defaults_to_text(self, fake_client):
        stdout, _, _ = run_cli(["get", "SID:Sheet1!A1"], fake_client)
        # text output format is "A1 value"
        assert "hello" in stdout
        assert "{" not in stdout  # not JSON

    def test_get_range_with_json_flag_prints_json(self, fake_client):
        stdout, _, _ = run_cli(["get", "SID:Sheet1!A1", "--format=json"], fake_client)
        assert '"values"' in stdout


# ================================ put =====================================


class TestCliPut:
    def test_put_scalar_sugar(self, fake_client):
        _, _, code = run_cli(["put", "SID:Sheet1!A1", "hello"], fake_client)
        assert code in (None, 0)
        fake_client.write.assert_called_once()
        ops = fake_client.write.call_args.args[1]
        assert ops == [{"range": "Sheet1!A1", "values": [["hello"]]}]

    def test_put_stdin_json(self, fake_client):
        _, _, _ = run_cli(["put", "SID:Sheet1"], fake_client,
                          stdin_text='{"A1": "x", "B1": 42}')
        ops = fake_client.write.call_args.args[1]
        ranges = {op["range"] for op in ops}
        assert ranges == {"Sheet1!A1", "Sheet1!B1"}

    def test_put_stdin_cell_value_text(self, fake_client):
        _, _, _ = run_cli(["put", "SID:Sheet1"], fake_client,
                          stdin_text="A1 hello\nB1 world\n")
        ops = fake_client.write.call_args.args[1]
        ranges = {op["range"] for op in ops}
        assert ranges == {"Sheet1!A1", "Sheet1!B1"}

    def test_put_silent_by_default(self, fake_client):
        stdout, _, _ = run_cli(["put", "SID:Sheet1!A1", "x"], fake_client)
        assert stdout == ""

    def test_put_json_flag_echoes_target(self, fake_client):
        stdout, _, _ = run_cli(
            ["put", "SID:Sheet1!A1", "x", "--format=json"], fake_client)
        assert '"target"' in stdout
        assert "SID:Sheet1!A1" in stdout

    def test_put_no_value_no_stdin_errors(self, fake_client):
        _, err, code = run_cli(["put", "SID:Sheet1!A1"], fake_client)
        assert code == 1
        assert "no value" in err.lower() or "no stdin" in err.lower()


# ================================ del =====================================


class TestCliDel:
    def test_del_range_clears(self, fake_client):
        _, _, _ = run_cli(["del", "SID:Sheet1!A1:B2"], fake_client)
        fake_client.clear.assert_called_once_with("SID", ["Sheet1!A1:B2"])

    def test_del_row_deletes_dimension(self, fake_client):
        _, _, _ = run_cli(["del", "SID:Sheet1!5"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        assert requests[0]["deleteDimension"]["range"]["dimension"] == "ROWS"

    def test_del_sheet_deletes_sheet(self, fake_client):
        _, _, _ = run_cli(["del", "SID:Sheet2"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        assert requests == [{"deleteSheet": {"sheetId": 42}}]

    def test_del_spreadsheet_calls_delete_spreadsheet(self, fake_client):
        _, _, _ = run_cli(["del", "SID"], fake_client)
        fake_client.delete_spreadsheet.assert_called_once_with("SID")

    def test_del_silent_by_default(self, fake_client):
        stdout, _, _ = run_cli(["del", "SID:Sheet1!A1:B2"], fake_client)
        assert stdout == ""


# ================================ new =====================================


class TestCliNew:
    def test_new_title(self, fake_client):
        stdout, _, _ = run_cli(["new", "My Title"], fake_client)
        fake_client.create.assert_called_once_with("My Title")
        # new always prints the result
        assert "NEW" in stdout

    def test_new_sheet(self, fake_client):
        _, _, _ = run_cli(["new", "SID:Dashboard"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        assert requests == [{"addSheet": {"properties": {"title": "Dashboard"}}}]

    def test_new_row_with_side(self, fake_client):
        _, _, _ = run_cli(["new", "SID:Sheet1!5", "--side=above"], fake_client)
        req = fake_client.meta_write.call_args.args[1][0]
        assert req["insertDimension"]["range"]["startIndex"] == 4
        assert req["insertDimension"]["inheritFromBefore"] is False

    def test_new_empty_creates_untitled(self, fake_client):
        _, _, _ = run_cli(["new"], fake_client)
        fake_client.create.assert_called_once_with("Untitled spreadsheet")


# =============================== copy =====================================


class TestCliCopy:
    def test_copy_same_spreadsheet_range_uses_server_side(self, fake_client):
        _, _, _ = run_cli(
            ["copy", "SID:Sheet1!A1:B2", ":Sheet2!D1:E2"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        assert "copyPaste" in requests[0]
        fake_client.read.assert_not_called()
        fake_client.write.assert_not_called()

    def test_copy_cross_spreadsheet_whole_sheet_uses_copyTo(self, fake_client):
        _, _, _ = run_cli(["copy", "SID1:Sheet1", "SID2"], fake_client)
        fake_client.copy_sheet_to.assert_called_once_with("SID1", 0, "SID2")

    def test_copy_inherits_sid_from_source(self, fake_client):
        # "!A1:B2" has no SID — must inherit from source
        _, _, _ = run_cli(
            ["copy", "SID:Sheet1!A1:B2", "!D1:E2"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        # Same-sheet copy: dest sheet == source sheet (Sheet1, sheetId=0)
        assert requests[0]["copyPaste"]["destination"]["sheetId"] == 0


# =============================== move =====================================


class TestCliMove:
    def test_move_row_uses_moveDimension(self, fake_client):
        _, _, _ = run_cli(["move", "SID:Sheet1!5", "!2"], fake_client)
        req = fake_client.meta_write.call_args.args[1][0]
        assert "moveDimension" in req
        assert req["moveDimension"]["destinationIndex"] == 1

    def test_move_same_ss_range_uses_cutPaste(self, fake_client):
        _, _, _ = run_cli(
            ["move", "SID:Sheet1!A1:B2", ":Sheet2!D1:E2"], fake_client)
        requests = fake_client.meta_write.call_args.args[1]
        assert "cutPaste" in requests[0]


# ============================== errors ====================================


class TestCliErrors:
    def test_grammar_error_exits_2(self, fake_client):
        # Missing SID on first operand
        _, err, code = run_cli(["get", ":Sheet1"], fake_client)
        assert code == 2
        assert "grammar" in err.lower()

    def test_unknown_verb_errors(self, fake_client):
        # argparse exits with code 2 for unknown subcommand
        _, _, code = run_cli(["frobnicate"], fake_client)
        assert code == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
