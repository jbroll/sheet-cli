"""Tests for the multi-call launcher — dispatch on basename(argv[0])."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import multicall


def test_drive_name_dispatches_to_drive_cli():
    with patch("drive_cli.cli.main") as drive_main, \
         patch("sheet_cli.cli.main") as sheet_main, \
         patch.object(sys, "argv", ["/usr/local/bin/drive-cli", "list"]):
        multicall.main()
        drive_main.assert_called_once()
        sheet_main.assert_not_called()


def test_sheet_name_dispatches_to_sheet_cli():
    with patch("drive_cli.cli.main") as drive_main, \
         patch("sheet_cli.cli.main") as sheet_main, \
         patch.object(sys, "argv", ["/usr/local/bin/sheet-cli", "get"]):
        multicall.main()
        sheet_main.assert_called_once()
        drive_main.assert_not_called()


def test_unknown_name_defaults_to_sheet_cli():
    with patch("drive_cli.cli.main") as drive_main, \
         patch("sheet_cli.cli.main") as sheet_main, \
         patch.object(sys, "argv", ["python", "get"]):
        multicall.main()
        sheet_main.assert_called_once()
        drive_main.assert_not_called()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
