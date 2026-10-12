# sheet-cli: `--file` input and a `batch` verb

## Purpose

Remove the reason sheet-cli's own docs recommend writing a Python generator script. Today bulk
input must arrive on stdin, and agents avoid `echo`/heredoc, so they default to a script. A file
input option lets an agent write the payload with its editor tool and hand over a path; a `batch`
verb lets one file express a whole sheet-build — values, formatting, and structure — in one
command.

## Scope

**In:** a `--file` option on the verbs that read a body; a new `batch` verb taking a sheet-name-aware
list of operations; documentation updates that replace the "write a script" advice.

**Out:** formula parsing or fill-down templates; new property types; changes to the
`sheet_client` library; changes to `drive-cli`.

## File input

`--file PATH` (alias `-f`) on `put`, `new`, and `batch`. The payload is read from `PATH` instead of
stdin. `--file -` reads stdin explicitly, so a caller can be deliberate rather than rely on the
fallback.

- `put` / `new`: the file's text goes through the existing `formats.parse_input`, so JSON and
  cell/value text both work as they do on stdin.
- `batch`: the file must be JSON.
- Supplying both a positional value (`put TARGET VALUE`) and `--file` is an error.
- A missing path, or a path that is a directory, is an error naming the path.

The stdin path stays exactly as it is; `--file` is an addition, not a replacement.

## The `batch` verb

```
sheet-cli batch SPREADSHEET_ID --file ops.json
```

The payload is a JSON **array of operations**. Each operation carries a locator and one or more
action keys.

Locators:

| Key | Form | Example |
|---|---|---|
| `range` | `Sheet!A1:B2` | `"Rosa House!A1:D35"` |
| `row` | `Sheet!5` | `"Rosa House!5"` |
| `column` | `Sheet!A` | `"Rosa House!A"` |

Actions:

| Action | Value | Applies to | Emits |
|---|---|---|---|
| `values` | 2-D array | range | `values.batchUpdate` entry |
| `clear` | `true` | range | `values.batchClear` entry |
| `format` | CellFormat object | range | `repeatCell` |
| `borders` | borders object | range | `updateBorders` |
| `note` | string | range | `repeatCell` (fields `note`) |
| `merge` | `true` or `"MERGE_ALL"`/`"MERGE_COLUMNS"`/`"MERGE_ROWS"` | range | `mergeCells` |
| `validation` | DataValidationRule | range | `setDataValidation` |
| `width` | pixels | column | `updateDimensionProperties` |
| `height` | pixels | row | `updateDimensionProperties` |

An operation may carry several actions at once, so a value write and its format travel together:

```json
[
  {"range": "Rosa House!A1:D35", "values": [["Total Value =>", "", "=B10", ""]]},
  {"range": "Rosa House!B6:B10", "format": {"numberFormat": {"type": "CURRENCY", "pattern": "\"$\"#,##0"}}},
  {"range": "Rosa House!A3", "format": {"textFormat": {"bold": true}}},
  {"column": "Rosa House!A", "width": 220},
  {"range": "Summary!C13", "values": [["=SUM(Summary!C9:C12)"]]}
]
```

The sheet title in every locator is required. `batch` targets a whole spreadsheet, so there is no
single sheet to inherit from, and an operation that silently defaulted to the first tab would be a
trap.

### Decomposition

`batch` builds two request lists from the operations, in file order within each:

- **values** — the `values` actions as a `values.batchUpdate` body, and the `clear` actions as a
  `values.batchClear` body.
- **requests** — everything else, as `spreadsheets.batchUpdate` requests.

Dispatch is up to three API calls: `values.batchUpdate` (if any writes), `values.batchClear` (if any
clears), then `spreadsheets.batchUpdate` (if any structural requests). They are not atomic across
the calls; the docs say so. A range's sheet title is resolved to a `sheetId` once per sheet and
cached for the run.

### Reuse

Decomposition goes through the same code the property handlers use, so there is one definition of
how a format becomes a `repeatCell`:

- `format` and `note` build their `fields` mask with `properties._fields_mask` (the same function
  `put .format` uses).
- `borders`, `validation`, `merge`, `width`, and `height` emit the same request shapes as their
  handlers in `properties.py`.
- Sheet-title resolution reuses the existing helper.

The handler bodies in `properties.py` are factored so the request-building step is callable without
a `Target`, and both `batch` and the handlers call it.

### Output

Silent like `put` and `del`. `--format=json` echoes `{"values": <response|null>, "requests":
<response|null>}`.

## Verification

- Unit tests (no network) for:
  - `--file` selection: file path, `-` for stdin, positional-plus-file conflict, missing path.
  - Decomposition: an ops list maps to the expected values bodies and batchUpdate requests,
    including a multi-action op and a `width` op.
- Existing tests still pass (`pytest`).
- Manual: build a small tab from one `ops.json` in a scratch spreadsheet.

## Documentation

The tool stops being "six verbs"; it becomes six verbs plus `batch`.

- `CLAUDE.md`: replace "Bulk cell operations with Python generation" with the `--file` + `batch`
  guidance; add `batch` to the grammar section.
- `llms.txt`: replace "Bulk writes — recommended pattern for agents" with the same; add `batch` and
  `--file`.
- `README.md`: add `batch` and `--file` to the CLI usage and examples.
- The `help` subcommand prints `llms.txt`, so it follows automatically.

## Risks and non-goals

- **Second input vocabulary.** The batch op schema is a parallel schema to the property targets. The
  mitigation is reuse: batch and the handlers share the request-builders, so the schema cannot drift
  from the handlers without a test failing.
- **Not atomic.** Values and structural requests are two API calls. Stated in the docs; a failure
  between them is reported by which call failed.
- **No fill-down.** Replicating a formula across rows still means the caller writes each row's
  formula. If that proves needed, it is a later, separate design; it would require parsing formulas,
  which the project currently disclaims.
