# Testing Guide

## Test layout

```
test/
├── test_grammar.py     # Target-string parse/resolve/classify/render
├── test_verbs.py       # do_get / do_put / do_del / do_new dispatch
├── test_dispatch.py    # do_copy / do_move server-side + fallbacks
├── test_cli.py         # End-to-end CLI through argparse
├── test_formats.py     # stdin/stdout formatters
├── test_client.py      # Utilities (A1, GridRange) and exception types
├── test_properties.py  # .property handlers (format, freeze, named, …)
├── test_retry.py       # 429/500/503 retry behavior + clear()
└── test_integration.py # Skipped unless SHEETS_TEST_SPREADSHEET_ID set
```

## Running tests

```bash
# Full unit suite (no credentials needed — integration tests are skipped)
venv/bin/python -m pytest test/

# With verbose output
venv/bin/python -m pytest test/ -v

# Single module
venv/bin/python -m pytest test/test_grammar.py -v

# Integration tests — require OAuth credentials and a real spreadsheet
export SHEETS_TEST_SPREADSHEET_ID=your-id-here
venv/bin/python -m pytest test/test_integration.py -v -s
```

The 10 integration tests skip without `SHEETS_TEST_SPREADSHEET_ID`.

## What each module verifies

**`test_grammar.py`** — parsing round-trips, inheritance shapes
(`Sheet!A1` → inherit SID, `!A1` → inherit SID+sheet, `:Sheet` → inherit SID),
quoted sheet names with `:` / `!` / spaces / apostrophes, classification of
ROW vs COLUMN vs RANGE vs CELL.

**`test_verbs.py`** — each verb's TargetType dispatch. For `do_put`: scalar
sugar, cell-keyed dict auto-qualified with target sheet, range-keyed dict,
bare 2D array, `!`-qualified keys pass through. Error cases for DRIVE /
SPREADSHEET puts, bad sides on row/column new, range on new.

**`test_dispatch.py`** — the copy/move branches:
- copy cross-spreadsheet whole sheet → `sheets.copyTo` (server-side)
- copy same-spreadsheet range → `copyPaste` batch (server-side)
- copy cross-spreadsheet range → read + write fallback
- copy whole spreadsheet → `drive.files.copy` (server-side; accepts a new
  title or empty DRIVE dest for the default "Copy of …")
- copy rejects self-copy when source and dest SID match
- move same-sheet row/col → `moveDimension` (server-side)
- move same-spreadsheet range → `cutPaste` (server-side)
- move cross-spreadsheet → copy + delete fallback

**`test_cli.py`** — argparse with `SheetsClient` mocked. Checks each verb's
wiring, scalar vs stdin `put`, JSON vs cell-value-text stdin parsing, text vs
JSON output, silent-by-default mutations, `--format=json` echo, grammar
error exit code 2, inheritance in copy/move second operand.

**`test_properties.py`** — `.property` handler dispatch for every registered
(name, scope) pair: range-level (format, borders, merge, note, validation,
protected), sheet-level (title, freeze, color, hidden, conditional[i]),
spreadsheet-level (title, named.NAME, parents / parents.FOLDER_ID), and
dimension-level (height, width). Verifies verb wiring (`get`/`put`/`del`/
`new`), scalar sugar, structured JSON bodies, collection semantics
(`put .parents` replaces via diff, `new .parents` adds, keyed `del` removes
one, unkeyed `del .parents` is refused to prevent orphaning), and that
`copy`/`move` reject `.property` targets.

**`test_retry.py`** — 429/500/503 exhaust retries, 400/404 no-retry, success
path, and `clear()` → `batchClear`.

## OAuth setup for integration tests

1. Create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console
2. Enable Google Sheets API and Google Drive API
3. Save credentials to `~/.sheet-cli/credentials.json`
4. Run `sheet-cli auth` once to cache the token
5. Create a test spreadsheet and export its ID as `SHEETS_TEST_SPREADSHEET_ID`

After that, `test_integration.py` will run against the real API.

## Adding tests

- Unit tests must not hit the network. Mock `SheetsClient` at the boundary
  (`test_verbs` / `test_dispatch`) or patch `sheet_cli.cli.SheetsClient` for
  CLI tests.
- Grammar-only changes go in `test_grammar.py`.
- Client method additions: write mock-based unit tests **and** add coverage
  to `test_integration.py` if the behavior can't be verified without the
  real API.
