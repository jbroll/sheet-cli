"""Multi-call launcher — one binary, behavior chosen by the name it's run as.

Both the ``sheet-cli`` and ``drive-cli`` console scripts point here; the
basename of ``argv[0]`` selects which sub-CLI to run (busybox-style). A name
starting with ``drive`` runs the Drive CLI; anything else runs the Sheets CLI.
"""

from __future__ import annotations

import os
import sys


def main():
    prog = os.path.basename(sys.argv[0] or "")
    if prog.startswith("drive"):
        from drive_cli.cli import main as drive_main
        return drive_main()
    from sheet_cli.cli import main as sheet_main
    return sheet_main()


if __name__ == "__main__":
    main()
