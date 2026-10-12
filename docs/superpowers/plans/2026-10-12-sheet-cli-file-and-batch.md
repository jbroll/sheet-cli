# sheet-cli `--file` and `batch` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan (inline execution, per the user's instruction). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--file` input option and a `batch` verb to sheet-cli so bulk writes and whole-sheet builds need a data file, not a generator script.

**Architecture:** Two new pure modules — `builders.py` (request-dict construction, shared by the property handlers and batch) and `batch.py` (a list of operations → a `BatchPlan` of values bodies, clear ranges, and batchUpdate requests). `cli.py` gains `--file` and a `batch` subcommand. No library changes.

**Tech Stack:** Python 3.8+, argparse, `sheet_client` (Google Sheets API v4), pytest.

## Global Constraints

- Package import root in tests is `src/` (tests do `sys.path.insert(0, .../src)`).
- Unit tests must not hit the network; mock `SheetsClient`.
- Follow the existing "thin pass-through, no opinions" style: no formula parsing, no templates.
- The tool's own docs (`CLAUDE.md`, `llms.txt`, `README.md`) must stop recommending a generator script; that is the point of the change.
- Run the suite with `venv/bin/python -m pytest test/`.

---

### Task 1: `builders.py` — shared request builders, and refactor `properties.py` onto them

**Files:**
- Create: `src/sheet_cli/builders.py`
- Modify: `src/sheet_cli/properties.py`
- Test: `test/test_builders.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `builders.fields_path(d: dict, prefix: str = "") -> list[str]`
  - `builders.fields_mask(d: dict, prefix: str = "") -> str`
  - `builders.format_request(grid_range: dict, fmt: dict) -> dict`
  - `builders.note_request(grid_range: dict, text: str) -> dict`
  - `builders.borders_request(grid_range: dict, borders: dict) -> dict`
  - `builders.validation_request(grid_range: dict, rule: dict) -> dict`
  - `builders.merge_request(grid_range: dict, merge_type: str) -> dict`
  - `builders.dimension_request(dimension_range: dict, pixels: int) -> dict`

- [ ] **Step 1: Write the failing test**

Create `test/test_builders.py`:

```python
"""Unit tests for the shared batchUpdate request builders."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import builders


def test_fields_mask_walks_to_leaves():
    mask = builders.fields_mask(
        {"textFormat": {"bold": True}, "backgroundColor": {"red": 1.0}},
        prefix="userEnteredFormat.",
    )
    assert set(mask.split(",")) == {
        "userEnteredFormat.textFormat.bold",
        "userEnteredFormat.backgroundColor.red",
    }


def test_format_request_sets_fields_mask():
    req = builders.format_request(
        {"sheetId": 3}, {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}
    )
    rc = req["repeatCell"]
    assert rc["range"] == {"sheetId": 3}
    assert rc["cell"] == {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}}
    assert rc["fields"] == (
        "userEnteredFormat.numberFormat.type,userEnteredFormat.numberFormat.pattern"
    )


def test_note_request_uses_note_field():
    req = builders.note_request({"sheetId": 0}, "hello")
    assert req["repeatCell"]["cell"] == {"note": "hello"}
    assert req["repeatCell"]["fields"] == "note"


def test_borders_request_merges_range():
    req = builders.borders_request({"sheetId": 0}, {"top": {"style": "SOLID"}})
    assert req["updateBorders"] == {"range": {"sheetId": 0}, "top": {"style": "SOLID"}}


def test_validation_request():
    rule = {"condition": {"type": "NUMBER_GREATER"}}
    req = builders.validation_request({"sheetId": 0}, rule)
    assert req["setDataValidation"] == {"range": {"sheetId": 0}, "rule": rule}


def test_merge_request():
    req = builders.merge_request({"sheetId": 0}, "MERGE_ALL")
    assert req["mergeCells"] == {"range": {"sheetId": 0}, "mergeType": "MERGE_ALL"}


def test_dimension_request_coerces_pixels_to_int():
    req = builders.dimension_request({"sheetId": 0}, "220")
    upd = req["updateDimensionProperties"]
    assert upd["properties"] == {"pixelSize": 220}
    assert upd["fields"] == "pixelSize"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest test/test_builders.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sheet_cli.builders'`

- [ ] **Step 3: Write `src/sheet_cli/builders.py`**

```python
"""Pure builders for spreadsheets.batchUpdate request bodies.

The property handlers in ``properties.py`` and the ``batch`` verb both turn a
payload into the same Google API request. Constructing them here means one
definition, so the two cannot drift.
"""

from __future__ import annotations

from typing import Any, Dict, List


def fields_path(d: Dict[str, Any], prefix: str = "") -> List[str]:
    """Walk ``d`` to its leaves and return dotted field paths.

    An empty dict terminates the walk and becomes a "replace this whole
    subtree" mask, matching Sheets API semantics for clearing.
    """
    paths: List[str] = []
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            paths.extend(fields_path(v, prefix=f"{path}."))
        else:
            paths.append(path)
    return paths


def fields_mask(d: Dict[str, Any], prefix: str = "") -> str:
    """Join leaf paths into a comma-separated field mask."""
    return ",".join(fields_path(d, prefix=prefix))


def format_request(grid_range: Dict[str, Any], fmt: Dict[str, Any]) -> Dict[str, Any]:
    return {"repeatCell": {
        "range": grid_range,
        "cell": {"userEnteredFormat": fmt},
        "fields": fields_mask(fmt, prefix="userEnteredFormat."),
    }}


def note_request(grid_range: Dict[str, Any], text: str) -> Dict[str, Any]:
    return {"repeatCell": {
        "range": grid_range,
        "cell": {"note": text},
        "fields": "note",
    }}


def borders_request(grid_range: Dict[str, Any], borders: Dict[str, Any]) -> Dict[str, Any]:
    return {"updateBorders": {"range": grid_range, **borders}}


def validation_request(grid_range: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    return {"setDataValidation": {"range": grid_range, "rule": rule}}


def merge_request(grid_range: Dict[str, Any], merge_type: str) -> Dict[str, Any]:
    return {"mergeCells": {"range": grid_range, "mergeType": merge_type}}


def dimension_request(dimension_range: Dict[str, Any], pixels: int) -> Dict[str, Any]:
    return {"updateDimensionProperties": {
        "range": dimension_range,
        "properties": {"pixelSize": int(pixels)},
        "fields": "pixelSize",
    }}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest test/test_builders.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Refactor `properties.py` onto the builders**

In `src/sheet_cli/properties.py`:

(a) Add the import near the other relative imports (after `from .grammar import (...)`):

```python
from . import builders
```

(b) Replace the bodies of `_fields_path` and `_fields_mask` (currently around lines 180–201) with aliases:

```python
_fields_path = builders.fields_path
_fields_mask = builders.fields_mask
```

(c) Replace `_format_put`'s body:

```python
def _format_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError("put .format requires a JSON object of format fields")
    return client.meta_write(
        target.spreadsheet_id,
        [builders.format_request(_grid_range(client, target), data)],
    )
```

(d) Replace `_note_put`'s body:

```python
def _note_put(client, target, data):
    text = data if isinstance(data, str) else str(data)
    return client.meta_write(
        target.spreadsheet_id,
        [builders.note_request(_grid_range(client, target), text)],
    )
```

(e) Replace `_borders_put`'s body:

```python
def _borders_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError(
            "put .borders requires a JSON object with top/bottom/left/right/"
            "innerHorizontal/innerVertical keys"
        )
    return client.meta_write(
        target.spreadsheet_id,
        [builders.borders_request(_grid_range(client, target), data)],
    )
```

(f) Replace `_validation_put`'s body:

```python
def _validation_put(client, target, data):
    if not isinstance(data, dict):
        raise GrammarError("put .validation requires a JSON object (DataValidationRule)")
    return client.meta_write(
        target.spreadsheet_id,
        [builders.validation_request(_grid_range(client, target), data)],
    )
```

(g) Replace `_merge_new`'s body:

```python
def _merge_new(client, target, data):
    merge_type = (data or "MERGE_ALL") if isinstance(data, str) else "MERGE_ALL"
    return client.meta_write(
        target.spreadsheet_id,
        [builders.merge_request(_grid_range(client, target), merge_type)],
    )
```

(h) Replace `_dim_size_put`'s inner `_put`:

```python
def _dim_size_put(dimension: str) -> Handler:
    def _put(client, target, data):
        dr = _dimension_range(client, target, dimension)
        return client.meta_write(
            target.spreadsheet_id,
            [builders.dimension_request(dr, int(data))],
        )
    return _put
```

- [ ] **Step 6: Run the full suite**

Run: `venv/bin/python -m pytest test/ -q`
Expected: PASS — all existing tests plus the 7 new ones, especially `test_properties.py` (which asserts the emitted request shapes are unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/sheet_cli/builders.py src/sheet_cli/properties.py test/test_builders.py
git commit -m "refactor: share batchUpdate request builders between properties and batch"
```

---

### Task 2: `batch.py` — operations list to a `BatchPlan`

**Files:**
- Create: `src/sheet_cli/batch.py`
- Test: `test/test_batch.py`

**Interfaces:**
- Consumes: `builders.*` from Task 1; `sheet_client.utils.a1_to_grid_range`, `column_to_index`; `grammar.parse`, `grammar.GrammarError`.
- Produces:
  - `batch.BatchPlan` dataclass with `values: list[dict]`, `clears: list[str]`, `requests: list[dict]`.
  - `batch.build_batch(ops: Any, resolve_sheet_id: Callable[[str], int]) -> BatchPlan`.

- [ ] **Step 1: Write the failing test**

Create `test/test_batch.py`:

```python
"""Unit tests for the batch verb's pure core."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_cli import batch
from sheet_cli.grammar import GrammarError


def _resolver(mapping):
    return lambda title: mapping[title]


def test_values_op():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}],
        _resolver({"Sheet1": 0}),
    )
    assert plan.values == [{"range": "Sheet1!A1:B2", "values": [[1, 2], [3, 4]]}]
    assert plan.clears == []
    assert plan.requests == []


def test_format_op_builds_repeat_cell_with_sheet_id():
    plan = batch.build_batch(
        [{"range": "Sheet1!B6:B10",
          "format": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}}],
        _resolver({"Sheet1": 42}),
    )
    rc = plan.requests[0]["repeatCell"]
    assert rc["range"]["sheetId"] == 42
    assert rc["range"]["startRowIndex"] == 5
    assert rc["range"]["endRowIndex"] == 10
    assert rc["fields"] == (
        "userEnteredFormat.numberFormat.type,userEnteredFormat.numberFormat.pattern"
    )


def test_width_op_requires_and_uses_column_locator():
    plan = batch.build_batch([{"column": "Sheet1!A", "width": 220}], _resolver({"Sheet1": 0}))
    upd = plan.requests[0]["updateDimensionProperties"]
    assert upd["range"] == {
        "sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1
    }
    assert upd["properties"] == {"pixelSize": 220}


def test_height_op_uses_row_locator():
    plan = batch.build_batch([{"row": "Sheet1!5", "height": 30}], _resolver({"Sheet1": 7}))
    upd = plan.requests[0]["updateDimensionProperties"]
    assert upd["range"] == {
        "sheetId": 7, "dimension": "ROWS", "startIndex": 4, "endIndex": 5
    }


def test_multi_action_op_splits_values_and_requests():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1", "values": [["x"]],
          "format": {"textFormat": {"bold": True}}}],
        _resolver({"Sheet1": 0}),
    )
    assert plan.values == [{"range": "Sheet1!A1", "values": [["x"]]}]
    assert plan.requests[0]["repeatCell"]["cell"] == {
        "userEnteredFormat": {"textFormat": {"bold": True}}
    }


def test_clear_op():
    plan = batch.build_batch(
        [{"range": "Sheet1!A1:Z9", "clear": True}], _resolver({"Sheet1": 0})
    )
    assert plan.clears == ["Sheet1!A1:Z9"]
    assert plan.values == []
    assert plan.requests == []


def test_sheet_id_resolved_once_per_sheet():
    calls = []

    def resolver(title):
        calls.append(title)
        return 0

    batch.build_batch(
        [
            {"range": "S!A1", "format": {"textFormat": {"bold": True}}},
            {"range": "S!B1", "format": {"textFormat": {"italic": True}}},
        ],
        resolver,
    )
    assert calls == ["S"]


def test_non_list_payload_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch({"range": "S!A1"}, _resolver({}))


def test_op_without_action_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "S!A1"}], _resolver({}))


def test_op_without_locator_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"values": [[1]]}], _resolver({}))


def test_locator_without_sheet_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "A1", "values": [[1]]}], _resolver({}))


def test_width_on_range_rejected():
    with pytest.raises(GrammarError):
        batch.build_batch([{"range": "S!A1", "width": 5}], _resolver({"S": 0}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest test/test_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sheet_cli.batch'`

- [ ] **Step 3: Write `src/sheet_cli/batch.py`**

```python
"""The ``batch`` verb's core: a list of operations -> values + batchUpdate requests.

Pure and testable. Sheet titles are resolved through an injected callable, so
tests pass a plain dict and the CLI passes a client-backed resolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from sheet_client.utils import a1_to_grid_range, column_to_index

from . import builders
from .grammar import GrammarError, parse

_LOCATORS = ("range", "row", "column")
_RANGE_ACTIONS = ("values", "clear", "format", "borders", "note", "merge", "validation")
_ALL_ACTIONS = (*_RANGE_ACTIONS, "width", "height")
_MERGE_TYPES = ("MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS")


@dataclass
class BatchPlan:
    values: List[Dict[str, Any]] = field(default_factory=list)
    clears: List[str] = field(default_factory=list)
    requests: List[Dict[str, Any]] = field(default_factory=list)


def _split_locator(locator: Any, where: str) -> Tuple[str, str]:
    """Split 'Sheet Title!A1:B2' into (sheet_title, local_locator)."""
    if not isinstance(locator, str) or "!" not in locator:
        raise GrammarError(f"{where}: locator must be 'Sheet!A1' form, got {locator!r}")
    parsed = parse(locator)
    if parsed.sheet is None or parsed.locator is None:
        raise GrammarError(f"{where}: locator needs a sheet and a range, got {locator!r}")
    return parsed.sheet, parsed.locator


def _column_dimension(sheet_id: int, col: str) -> Dict[str, Any]:
    idx = column_to_index(col)
    return {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1}


def _row_dimension(sheet_id: int, row: str) -> Dict[str, Any]:
    try:
        idx = int(row) - 1
    except (TypeError, ValueError):
        raise GrammarError(f"row locator must be a number, got {row!r}")
    return {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": idx, "endIndex": idx + 1}


def _merge_type(value: Any) -> str:
    if value is True:
        return "MERGE_ALL"
    if isinstance(value, str) and value.upper() in _MERGE_TYPES:
        return value.upper()
    raise GrammarError(f"merge must be true or one of {_MERGE_TYPES}, got {value!r}")


def build_batch(ops: Any, resolve_sheet_id: Callable[[str], int]) -> BatchPlan:
    """Turn a list of operation objects into a BatchPlan.

    Each op has exactly one locator (``range``, ``row``, or ``column``) naming a
    sheet, and at least one action. Actions on a ``range`` locator: values,
    clear, format, borders, note, merge, validation. ``width`` needs a column
    locator; ``height`` needs a row locator.
    """
    if not isinstance(ops, list):
        raise GrammarError("batch payload must be a JSON array of operations")

    plan = BatchPlan()
    cache: Dict[str, int] = {}

    def sid_for(sheet: str) -> int:
        if sheet not in cache:
            cache[sheet] = resolve_sheet_id(sheet)
        return cache[sheet]

    for i, op in enumerate(ops):
        where = f"op {i}"
        if not isinstance(op, dict):
            raise GrammarError(f"{where}: must be a JSON object")

        locators = [k for k in _LOCATORS if k in op]
        if len(locators) != 1:
            raise GrammarError(f"{where}: exactly one of {_LOCATORS} is required")
        loc = locators[0]

        actions = [k for k in _ALL_ACTIONS if k in op and (k != "clear" or op[k])]
        if not actions:
            raise GrammarError(
                f"{where}: no action (one of {_ALL_ACTIONS} is required)"
            )

        sheet, local = _split_locator(op[loc], where)

        for act in actions:
            if act == "width":
                if loc != "column":
                    raise GrammarError(f"{where}: width requires a column locator")
                plan.requests.append(
                    builders.dimension_request(_column_dimension(sid_for(sheet), local), int(op[act]))
                )
                continue
            if act == "height":
                if loc != "row":
                    raise GrammarError(f"{where}: height requires a row locator")
                plan.requests.append(
                    builders.dimension_request(_row_dimension(sid_for(sheet), local), int(op[act]))
                )
                continue
            if loc != "range":
                raise GrammarError(f"{where}: {act} requires a range locator")
            if act == "values":
                plan.values.append({"range": op[loc], "values": op["values"]})
                continue
            if act == "clear":
                plan.clears.append(op[loc])
                continue
            grid = a1_to_grid_range(local, sheet_id=sid_for(sheet))
            if act == "format":
                plan.requests.append(builders.format_request(grid, op["format"]))
            elif act == "borders":
                plan.requests.append(builders.borders_request(grid, op["borders"]))
            elif act == "note":
                plan.requests.append(builders.note_request(grid, op["note"]))
            elif act == "validation":
                plan.requests.append(builders.validation_request(grid, op["validation"]))
            elif act == "merge":
                plan.requests.append(builders.merge_request(grid, _merge_type(op["merge"])))

    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest test/test_batch.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sheet_cli/batch.py test/test_batch.py
git commit -m "feat(batch): build values and batchUpdate requests from an ops list"
```

---

### Task 3: CLI — `--file` on `put`/`new`, and the `batch` verb

**Files:**
- Modify: `src/sheet_cli/cli.py`
- Modify: `src/sheet_cli/__init__.py` (only if it re-exports submodules — check; otherwise skip)
- Test: `test/test_cli.py`

**Interfaces:**
- Consumes: `batch.build_batch` from Task 2; `verbs._resolve_sheet_id`; `formats.read_stdin`, `formats.parse_input`.
- Produces: `cli.cmd_batch`, `cli._read_input_source`, `cli._add_file_arg`.

- [ ] **Step 1: Write the failing tests**

Open `test/test_cli.py`. Add `import json` to the imports at the top (after `import io`). Then append at the end of the file:

```python
# ============================== --file ====================================
def test_put_reads_payload_from_file(fake_client, tmp_path):
    f = tmp_path / "cells.json"
    f.write_text('{"A1": "hi", "B1": 42}')
    out, err, code = run_cli(["put", "SID:Sheet1", "--file", str(f)], fake_client)
    assert code is None
    fake_client.write.assert_called_once()
    ops = fake_client.write.call_args[0][1]
    assert {"range": "Sheet1!A1", "values": [["hi"]]} in ops


def test_put_missing_file_is_grammar_error(fake_client):
    out, err, code = run_cli(["put", "SID:Sheet1", "--file", "/no/such/file"], fake_client)
    assert code == 2
    assert "not a readable file" in err


def test_put_scalar_and_file_conflict(fake_client, tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}")
    out, err, code = run_cli(["put", "SID:Sheet1!A1", "hi", "--file", str(f)], fake_client)
    assert code == 2
    assert "cannot combine" in err


# ============================== batch =====================================
def test_batch_applies_values_and_requests(fake_client, tmp_path):
    ops = [
        {"range": "Sheet1!A1", "values": [["hi"]]},
        {"range": "Sheet1!A1", "format": {"textFormat": {"bold": True}}},
        {"column": "Sheet1!A", "width": 100},
    ]
    f = tmp_path / "ops.json"
    f.write_text(json.dumps(ops))
    out, err, code = run_cli(["batch", "SID", "--file", str(f)], fake_client)
    assert code is None
    fake_client.write.assert_called_once()
    fake_client.meta_write.assert_called_once()
    reqs = fake_client.meta_write.call_args[0][1]
    assert reqs[0]["repeatCell"]["range"]["sheetId"] == 0
    assert reqs[1]["updateDimensionProperties"]["properties"]["pixelSize"] == 100


def test_batch_clear_calls_clear(fake_client, tmp_path):
    f = tmp_path / "ops.json"
    f.write_text(json.dumps([{"range": "Sheet1!A1:Z9", "clear": True}]))
    out, err, code = run_cli(["batch", "SID", "--file", str(f)], fake_client)
    assert code is None
    fake_client.clear.assert_called_once()
    assert fake_client.clear.call_args[0][1] == ["Sheet1!A1:Z9"]


def test_batch_json_echo(fake_client, tmp_path):
    f = tmp_path / "ops.json"
    f.write_text(json.dumps([{"range": "Sheet1!A1", "values": [["x"]]}]))
    out, err, code = run_cli(["batch", "SID", "--file", str(f), "--format", "json"], fake_client)
    assert code is None
    assert '"values"' in out


def test_batch_invalid_json_is_grammar_error(fake_client, tmp_path):
    f = tmp_path / "ops.json"
    f.write_text("{not json")
    out, err, code = run_cli(["batch", "SID", "--file", str(f)], fake_client)
    assert code == 2
    assert "invalid JSON" in err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest test/test_cli.py -k "file or batch" -v`
Expected: FAIL — `SystemExit`/unknown subcommand `batch`, and `--file` unrecognized.

- [ ] **Step 3: Implement `--file` and `batch` in `cli.py`**

(a) Add `batch` to the module imports (line 39):

```python
from . import batch, dispatch, formats, verbs
```

(b) Replace `_read_data_from_stdin` (around lines 121–125) with:

```python
def _read_input_source(args) -> str:
    """Return the payload text: from ``--file PATH`` if given, else stdin.

    ``--file -`` reads stdin explicitly.
    """
    path = getattr(args, "file", None)
    if path is None or path == "-":
        return formats.read_stdin()
    p = Path(path)
    if not p.is_file():
        raise GrammarError(f"--file: not a readable file: {path}")
    return p.read_text()
```

(c) Replace `cmd_put`'s body:

```python
def cmd_put(args):
    client = SheetsClient()
    target = _parse_target(args.target)

    if args.value is not None:
        if getattr(args, "file", None) is not None:
            raise GrammarError("put: cannot combine a positional value with --file")
        data: Any = args.value
    else:
        text = _read_input_source(args)
        data = formats.parse_input(text) if text else None
        # Property targets may accept no body (e.g. ``.autofit``). Value
        # writes still require explicit data.
        if data is None and target.property is None:
            print("put: no value given and no input", file=sys.stderr)
            sys.exit(1)

    response = verbs.do_put(client, target, data)
    _emit_mutation(target, response, args.format == "json")
```

(d) Replace `cmd_new`'s body lines that read stdin:

```python
def cmd_new(args):
    client = SheetsClient()
    target = _parse_target(args.target or "")
    # Property collections (e.g. `.conditional`, `.named`) take a body.
    if target.property is not None:
        text = _read_input_source(args)
        data = formats.parse_input(text) if text else None
    else:
        data = None
    response = verbs.do_new(client, target, side=args.side, data=data)
    _print_json(response)
```

(e) Add `cmd_batch` after `cmd_move`:

```python
def cmd_batch(args):
    client = SheetsClient()
    sid = args.spreadsheet_id
    text = _read_input_source(args)
    if not text.strip():
        raise GrammarError("batch: no operations given (use --file or stdin)")
    try:
        ops = json.loads(text)
    except json.JSONDecodeError as e:
        raise GrammarError(f"batch: invalid JSON: {e}")

    plan = batch.build_batch(ops, lambda title: verbs._resolve_sheet_id(client, sid, title))

    responses: dict = {}
    if plan.values:
        responses["values"] = client.write(sid, plan.values)
    if plan.clears:
        responses["clears"] = client.clear(sid, plan.clears)
    if plan.requests:
        responses["requests"] = client.meta_write(sid, plan.requests)
    if args.format == "json":
        _print_json(responses)
```

(f) In `main()`, add a `_add_file_arg` helper next to `add_format`:

```python
    def add_file(p):
        p.add_argument("--file", "-f", default=None, metavar="PATH",
                       help="read the payload from PATH ('-' for stdin) instead of stdin")
```

(g) Wire `add_file` onto `put` and `new`, and add the `batch` subparser. In `main()`, after `add_format(p_put); p_put.set_defaults(func=cmd_put)` add `add_file(p_put)`. For `new`, after `p_new.set_defaults(func=cmd_new)` add `add_file(p_new)`. Then, before `p_auth`, add:

```python
    p_batch = sub.add_parser("batch", help="apply a JSON list of operations in one call")
    p_batch.add_argument("spreadsheet_id", help="spreadsheet ID")
    add_file(p_batch)
    add_format(p_batch)
    p_batch.set_defaults(func=cmd_batch)
```

(h) Update the module docstring verb list (lines 3–12) to add:

```
    batch  SID --file ops.json   apply a list of operations in one call
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/python -m pytest test/test_cli.py -v`
Expected: PASS — the new `--file` and `batch` tests plus the existing CLI tests.

- [ ] **Step 5: Run the full suite**

Run: `venv/bin/python -m pytest test/ -q`
Expected: PASS.

- [ ] **Step 6: Smoke-test against the CLI help**

Run: `venv/bin/python -m sheet_cli batch --help`
Expected: usage line showing `--file PATH` and the `spreadsheet_id` positional.

- [ ] **Step 7: Commit**

```bash
git add src/sheet_cli/cli.py test/test_cli.py
git commit -m "feat(cli): --file input and a batch verb"
```

---

### Task 4: Documentation — drop the "write a script" advice

**Files:**
- Modify: `CLAUDE.md`
- Modify: `llms.txt`
- Modify: `README.md`
- Delete: `docs/superpowers/specs/2026-10-12-sheet-cli-file-and-batch-design.md` (folded into the docs above)

- [ ] **Step 1: Update `CLAUDE.md`**

(a) In the "CLI Grammar (v2)" section, change the lead line from "Six verbs over one target-string grammar:" to "Verbs over one target-string grammar (the six original verbs plus `batch`):" and add to the verb list:

```
batch  SID --file ops.json  apply a JSON list of operations in one call
```

(b) Replace the entire "**Bulk cell operations with Python generation:**" subsection (through its closing guidance line "Prefer the Write tool for generating the script (avoids heredoc approval prompts).") with:

```markdown
**Bulk writes with `--file`:**

Pass a JSON payload from a file instead of stdin — no heredoc, no generator
script. Write the file with the Write tool, then:

```bash
sheet-cli put SPREADSHEET_ID:Sheet1 --file cells.json
```

Keys are A1 addresses relative to the target sheet:

```json
{"A1": "Name", "B1": 42, "C1": "=A1&B1"}
```

**Building a sheet with `batch`:**

One file, one command, values + formatting + structure:

```bash
sheet-cli batch SPREADSHEET_ID --file ops.json
```

`ops.json` is a list of operations. Each names a sheet and a range (or a row /
column) and carries one or more actions:

```json
[
  {"range": "Sheet1!A1:D35", "values": [["Total", "", "=B10", ""]]},
  {"range": "Sheet1!B6:B10", "format": {"numberFormat": {"type": "CURRENCY", "pattern": "\"$\"#,##0"}}},
  {"column": "Sheet1!A", "width": 220}
]
```

Actions: `values`, `clear`, `format`, `borders`, `note`, `merge`,
`validation`, `width`, `height`. Value writes go to `values.batchUpdate`,
clears to `values.batchClear`, and the rest to `spreadsheets.batchUpdate` —
three calls at most, not atomic across them. A file written on stdin
(`--file -`) works anywhere `--file` does.
```

- [ ] **Step 2: Update `llms.txt`**

(a) Add to the Quick reference block:

```
sheet-cli batch  SID --file ops.json   apply a list of operations in one call
```

(b) Add `--file PATH` to the Input formats section, e.g. as a lead sentence: "`put`, `new`, and `batch` also accept `--file PATH` (or `--file -` for stdin) to read the payload from a file."

(c) Replace the whole "## Bulk writes — recommended pattern for agents" section (through the "Scales to thousands of cells in a single call." line) with:

```markdown
## Bulk writes — recommended pattern for agents

Write the payload to a file with the editor tool and pass `--file`; never
reach for `echo`/heredoc, and never write a generator script.

```bash
sheet-cli put SID:Sheet1 --file cells.json       # cell-keyed, relative to the sheet
sheet-cli batch SID --file ops.json              # values + formatting + structure
```

`cells.json` is cell- or range-keyed:

```json
{"A1": "hello", "B1": 42, "C1": "=SUM(A1:B1)"}
{"A1:B2": [[1, 2], [3, 4]]}
```

`ops.json` is a list of operations, each naming a sheet and a range (or a row
/ column) with one or more actions (`values`, `clear`, `format`, `borders`,
`note`, `merge`, `validation`, `width`, `height`):

```json
[{"range": "Sheet1!B6:B10",
  "format": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}}]
```
```

- [ ] **Step 3: Update `README.md`**

(a) In the CLI Usage verb list, add:

```
sheet-cli batch  SID --file ops.json   apply a list of operations in one call
```

(b) In the Examples block, add:

```bash
# Bulk write from a file (no heredoc, no script)
sheet-cli put SID:Sheet1 --file cells.json

# A whole sheet-build — values, formatting, structure — in one call
sheet-cli batch SID --file ops.json
```

(c) Add `--file PATH` to the `.property` / input-format notes where stdin is described.

- [ ] **Step 4: Verify no "script" advice remains**

Run: `grep -rn "gen.py\|generator script\|write a script" CLAUDE.md llms.txt README.md`
Expected: no matches.

- [ ] **Step 5: Retire the spec**

```bash
git rm docs/superpowers/specs/2026-10-12-sheet-cli-file-and-batch-design.md
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md llms.txt README.md
git commit -m "docs: --file and batch replace the generator-script advice"
```

---

## Self-Review

**Spec coverage:** `--file` on put/new/batch with `-` for stdin and a
positional/file conflict ✓ (Task 3); a sheet-name-aware ops list with the core
action set ✓ (Task 2); decomposition into values/clear/batchUpdate with
per-sheet id caching ✓ (Task 2); reuse of the property request builders ✓
(Task 1); silent output with `--format=json` echo ✓ (Task 3); docs updated and
spec retired ✓ (Task 4); unit tests for file selection and decomposition ✓
(Tasks 1–3).

**Placeholder scan:** no TBD/TODO; every code step carries full code.

**Type consistency:** `builders.*` names match between Task 1's definitions and
Task 2's calls; `BatchPlan.values/clears/requests` match between `batch.py`,
`cli.cmd_batch`, and the tests; `verbs._resolve_sheet_id(client, sid, title)`
signature matches its existing definition in `verbs.py`.
