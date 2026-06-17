# drive-cli — a Drive-native sibling CLI

**Date:** 2026-06-16
**Status:** Approved, ready for implementation
**Supersedes:** the CLI/dispatch portions of `2026-06-16-drive-copy-design.md`
(the library primitives from that spec are kept; the `sheet-cli copy --into`
surface is withdrawn).

## Motivation

Drive operations address resources by **Drive file/folder ID**, which does not
fit sheet-cli's `SID:Sheet!locator` TARGET grammar. Bolting generic file/folder
copy and folder creation onto `sheet-cli`'s `copy`/`new` verbs muddied that
grammar (a `--into` flag, a `sheet|folder` type keyword clashing with
"sheet = tab"). Instead, Drive-native operations move to their own multi-call
executable, `drive-cli`, leaving sheet-cli's grammar clean.

## Decisions

- Whole-spreadsheet copy (`sheet-cli copy SID "Title"` → Drive `files.copy`)
  **stays in sheet-cli** — its operand is a SID and it fits the grammar.
- First cut of `drive-cli` includes `copy`, `new`, `move`, `list`, and
  `parents`.
- The destination folder is an optional positional argument, not a `--into`
  flag.

## drive-cli command surface

Targets are plain Drive IDs. The destination folder is an **optional positional
argument** (no `--into` flag), keeping the surface uniform across verbs.

```
drive-cli list    [FOLDER]                  list files (root, or inside FOLDER)
drive-cli copy    ID [FOLDER] [--name NAME] copy file/folder, optionally into FOLDER
drive-cli new     folder NAME [FOLDER]      create a folder, optionally inside FOLDER
drive-cli new     sheet  NAME [FOLDER]      create a spreadsheet, optionally inside FOLDER
drive-cli move    ID FOLDER [--add]         move into FOLDER (--add keeps existing parents)
drive-cli parents ID                        list the folders containing ID
drive-cli auth                              OAuth login (shared token)
```

Behavior:
- `copy ID [FOLDER]` probes the source mimeType: folder → `copy_folder`
  (recursive); spreadsheet → `copy_spreadsheet` (sheet-shaped result); other →
  `copy_file`. `--name` sets the new title; the positional `FOLDER` is the
  destination folder.
- `new folder NAME [FOLDER]` → `create_folder`.
  `new sheet NAME [FOLDER]` → `create` with folder placement.
- `move ID FOLDER` relocates: `update_parents(add=[FOLDER], remove=<current>)`.
  `--add` adds `FOLDER` without removing existing parents (multi-parent).
- `parents ID` lists the folder IDs containing the file (read-only;
  `update_parents` writes are reached via `move`).
- `list` with no arg lists Drive files at root; with `FOLDER` lists that
  folder's direct children.

Output: mutations (`copy`/`new`/`move`) print JSON; `list` and `parents` print
text by default with `--format=json` for raw shape — mirroring sheet-cli's
text-first reads.

## Packaging

- New package `src/drive_cli/`:
  - `ops.py` — pure verb functions (`do_list`, `do_copy`, `do_new`, `do_move`,
    `do_parents`) taking `(client, ...)` and returning raw dicts/lists. This is
    the shared core called by **both** the CLI and the MCP server (mirrors how
    `sheet_cli` shares `verbs.py`/`dispatch.py`).
  - `cli.py` — argparse entry point that parses positional IDs/folders and
    delegates to `ops`.
- Multi-call binary: a single launcher `sheet_cli/multicall.py` dispatches on
  `basename(argv[0])` (name starting with `drive` → Drive CLI, else Sheets
  CLI). Both `setup.py` console scripts (`sheet-cli`, `drive-cli`) point at
  `sheet_cli.multicall:main` — one binary, two names, not a separate
  executable. `find_packages(where='src')` discovers the `drive_cli` package.
- Shares the `sheet_client` library and the cached OAuth token
  (`~/.sheet-cli/token.json`).

## MCP surface

The existing MCP server (`mcp-server/sheet-service.py`) gains a parallel set of
`drive_*` tools, each delegating to `drive_cli.ops` so CLI and MCP stay in
lockstep:

| MCP tool | ops function | arguments |
|---|---|---|
| `drive_list` | `do_list` | `folder?` |
| `drive_copy` | `do_copy` | `id`, `folder?`, `name?` |
| `drive_new` | `do_new` | `kind` (`folder`\|`sheet`), `name`, `folder?` |
| `drive_move` | `do_move` | `id`, `folder`, `add?` |
| `drive_parents` | `do_parents` | `id` |

The `sheets_copy` `into_folder` argument added earlier this session is reverted
(that surface is withdrawn from sheet-cli). The `test_server.py` expected-tools
list is updated to include the new `drive_*` tools.

## Library changes (`src/sheet_client/client.py`)

Kept from the prior spec: `get_file_mime`, `copy_file`, `copy_folder`.

New / changed:
- Promote `_create_folder` → public `create_folder(name,
  parent_folder_id=None) -> {id, name, parents, url}`. `copy_folder` keeps
  calling it.
- `create(title, sheets=None, parent_folder_id=None)` — when
  `parent_folder_id` is set, place the new spreadsheet in that folder (create,
  then `update_parents(add=[folder], remove=current)` to move it out of root).
- `list_files(folder_id=None, include_shared_drives=False) -> List[dict]` —
  generic Drive listing (`id, name, mimeType`), paginated. `list_spreadsheets`
  stays for sheet-cli's Drive listing.
- `get_parents` / `update_parents` already exist; reused by `drive-cli parents`.

## sheet-cli reverts

Back out this session's additions that touched the grammar:
- `cli.py`: remove the `--into` flag and the optional-`dest` handling from
  `copy`; restore `cmd_copy` to its prior form (required `dest`).
- `dispatch.py`: remove `into_folder`, `_drive_copy`, and the mime constants;
  restore the original whole-spreadsheet branch (`copy SID "Title"` →
  `copy_spreadsheet`).
- `mcp-server/sheet-service.py`: revert the `sheets_copy` `into_folder` arg.
- Tests: remove the `copy --into` cases from `test_cli.py` / `test_dispatch.py`,
  restoring those files to their prior copy behavior.
- Docs: remove `--into` from sheet-cli `copy` help/examples (`CLAUDE.md`,
  `README.md`, `llms.txt`, sheet-cli sections of `API.md`).

Kept: all `client.py` primitives and their `test_client.py` tests.

## Testing (TDD)

- `test/test_drive_ops.py` — the shared `ops` functions against a mocked
  `SheetsClient`: `do_copy` file vs folder vs spreadsheet routing + name/folder;
  `do_new` folder vs sheet with/without folder; `do_move` relocate vs `--add`;
  `do_list` root vs folder; `do_parents`.
- `test/test_drive_cli.py` — argparse routing + delegation against a mocked
  client (mirrors `test_cli.py`'s `run_cli` harness): each verb's positional
  parsing, `--name`/`--add` flags, optional folder, unknown verb errors.
- `mcp-server/test_server.py` — updated expected-tools list; a smoke call for a
  `drive_*` tool.
- `test/test_client.py` — add `create_folder`, `create(..., parent_folder_id)`,
  and `list_files` tests; keep the existing primitive tests.
- Confirm reverted sheet-cli copy tests pass unchanged.

## Docs

- New `drive-cli` section in `README.md`; its own `llms.txt`-style reference (or
  a section). Document `create_folder` / `list_files` / `create` folder
  placement in `API.md`. Note `drive-cli` in `CLAUDE.md`.
- MCP Drive tools (separate `drive_*` tools) are a possible follow-up, out of
  scope for this cut.
```
