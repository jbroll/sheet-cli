# Folder-Scoped Drive Listing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `folder_id` parameter to Drive listing so agents can scope `sheets_get`/`sheet-cli get` to a specific folder without writing custom Python.

**Architecture:** Three-layer change threading through the stack — `SheetsClient.list_spreadsheets()` gains a `folder_id` kwarg that prepends a Drive query clause; `verbs.do_get()` passes it through; MCP and CLI each expose it to callers. No new files needed.

**Tech Stack:** Python 3.8+, `unittest.mock`, `pytest`, Google Drive API v3 query syntax.

---

### Task 1: Add `folder_id` to `SheetsClient.list_spreadsheets()`

**Files:**
- Modify: `src/sheet_client/client.py` (around line 466)
- Test: `test/test_client.py`

- [ ] **Step 1: Write the failing tests**

Add this class to `test/test_client.py`:

```python
class TestListSpreadsheets:
    def _make_client_with_drive(self, response):
        """Return a SheetsClient instance with a mocked drive service."""
        from unittest.mock import MagicMock
        from sheet_client.client import SheetsClient

        mock_drive = MagicMock()
        mock_drive.files.return_value.list.return_value.execute.return_value = response

        client = SheetsClient.__new__(SheetsClient)
        client.drive = mock_drive
        client._execute_with_retry = MagicMock(return_value=response)
        return client, mock_drive

    def test_no_folder_id_query_has_no_parent_filter(self):
        client, mock_drive = self._make_client_with_drive({"files": []})
        client.list_spreadsheets()
        call_kwargs = mock_drive.files.return_value.list.call_args[1]
        assert "'in parents'" not in call_kwargs['q']
        assert "in parents" not in call_kwargs['q']

    def test_folder_id_prepends_parent_clause(self):
        files = [{"id": "abc", "name": "Sheet"}]
        client, mock_drive = self._make_client_with_drive({"files": files})
        result = client.list_spreadsheets(folder_id="FOLDER123")
        call_kwargs = mock_drive.files.return_value.list.call_args[1]
        assert "'FOLDER123' in parents" in call_kwargs['q']
        assert result == files
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/john/src/sheet-cli
venv/bin/pytest test/test_client.py::TestListSpreadsheets -v
```

Expected: `FAILED` — `list_spreadsheets` does not accept `folder_id`.

- [ ] **Step 3: Implement `folder_id` in `list_spreadsheets()`**

In `src/sheet_client/client.py`, replace the `list_spreadsheets` method (around line 466):

```python
def list_spreadsheets(self, folder_id: Optional[str] = None,
                      include_shared_drives: bool = False) -> List[dict]:
    """List spreadsheets visible to the authenticated user.

    Args:
        folder_id: Drive folder ID. When set, returns only spreadsheets
                   directly inside that folder.
        include_shared_drives: If True, also search Shared Drives.

    Returns:
        List of file metadata dicts (all pages merged):
        [{'id': '...', 'name': '...', 'modifiedTime': '...', 'owners': [...], 'shared': bool}]
    """
    files = []
    page_token = None
    query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    if folder_id:
        query = f"'{folder_id}' in parents and {query}"

    while True:
        kwargs = {
            'q': query,
            'fields': 'nextPageToken, files(id,name,modifiedTime,owners,shared)',
            'pageSize': 1000,
        }
        if page_token:
            kwargs['pageToken'] = page_token
        if include_shared_drives:
            kwargs['includeItemsFromAllDrives'] = True
            kwargs['supportsAllDrives'] = True

        request = self.drive.files().list(**kwargs)
        response = self._execute_with_retry(request)
        files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return files
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest test/test_client.py::TestListSpreadsheets -v
```

Expected: both tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/sheet_client/client.py test/test_client.py
git commit -m "feat: add folder_id param to list_spreadsheets()"
```

---

### Task 2: Thread `folder_id` through `verbs.do_get()`

**Files:**
- Modify: `src/sheet_cli/verbs.py` (line 67)
- Test: `test/test_verbs.py`

- [ ] **Step 1: Write the failing tests**

Add to the `TestDoGet` class in `test/test_verbs.py`:

```python
def test_drive_with_folder_id_passes_folder_id_to_list_spreadsheets(self, client):
    client.list_spreadsheets.return_value = [{"id": "x"}]
    result = do_get(client, Target(None, None, None), folder_id="FOLDER123")
    client.list_spreadsheets.assert_called_once_with(folder_id="FOLDER123")
    assert result == [{"id": "x"}]

def test_drive_without_folder_id_passes_none(self, client):
    client.list_spreadsheets.return_value = []
    do_get(client, Target(None, None, None))
    client.list_spreadsheets.assert_called_once_with(folder_id=None)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
venv/bin/pytest test/test_verbs.py::TestDoGet::test_drive_with_folder_id_passes_folder_id_to_list_spreadsheets test/test_verbs.py::TestDoGet::test_drive_without_folder_id_passes_none -v
```

Expected: `FAILED` — `do_get` does not accept `folder_id` kwarg.

- [ ] **Step 3: Update `do_get` signature and DRIVE branch**

In `src/sheet_cli/verbs.py`, check the existing imports:

```bash
grep "^from typing" src/sheet_cli/verbs.py
```

If `Optional` is missing from the `from typing import ...` line, add it. Then update `do_get` (line 67):

```python
def do_get(client: SheetsClient, target: Target,
           folder_id: Optional[str] = None) -> Any:
    """Read what's at the target. Returns the raw API response.

    - DRIVE        → list of spreadsheet file metadata
    - SPREADSHEET  → full meta_read() response
    - SHEET        → values.get response for the whole sheet
    - RANGE/ROW/COL→ values.get response for the locator
    """
    if target.property is not None:
        from . import properties
        return properties.dispatch("get", client, target, None)

    tt = classify(target)

    if tt == TargetType.DRIVE:
        return client.list_spreadsheets(folder_id=folder_id)

    assert target.spreadsheet_id is not None

    if tt == TargetType.SPREADSHEET:
        return client.meta_read(target.spreadsheet_id)

    a1 = a1_range_for_locator(target)
    return client.read(
        target.spreadsheet_id,
        [a1],
        types=CellData.VALUE | CellData.FORMULA,
    )
```

- [ ] **Step 4: Run all `TestDoGet` tests to confirm they pass**

```bash
venv/bin/pytest test/test_verbs.py::TestDoGet -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/sheet_cli/verbs.py test/test_verbs.py
git commit -m "feat: thread folder_id through do_get()"
```

---

### Task 3: Expose `--folder` in the CLI `get` command

**Files:**
- Modify: `src/sheet_cli/cli.py` (lines 131–135 and 250–254)
- Test: `test/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `test/test_cli.py` (uses the existing `run_cli` helper and `fake_client` fixture already in that file):

```python
def test_get_folder_flag_forwarded_to_list_spreadsheets(fake_client):
    """--folder FOLDER_ID causes list_spreadsheets to be called with folder_id."""
    fake_client.list_spreadsheets.return_value = []
    run_cli(["get", "--folder", "FOLDER123"], fake_client)
    fake_client.list_spreadsheets.assert_called_once_with(folder_id="FOLDER123")


def test_get_folder_with_non_drive_target_exits_error(fake_client):
    """--folder on a non-empty (non-DRIVE) target must exit with code 2."""
    _, stderr, code = run_cli(["get", "SOMESID:Sheet1", "--folder", "FOLDER123"], fake_client)
    assert code == 2
    assert "folder" in stderr.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
venv/bin/pytest test/test_cli.py::test_get_folder_flag_forwarded_to_list_spreadsheets test/test_cli.py::test_get_folder_with_non_drive_target_exits_error -v
```

Expected: `FAILED` — `--folder` is not a recognized argument.

- [ ] **Step 3: Add `--folder` to the `get` subparser and update `cmd_get`**

In `src/sheet_cli/cli.py`, update the `get` subparser block (around line 250) to add the `--folder` argument:

```python
p_get = sub.add_parser("get", help="read cells / metadata / drive listing")
p_get.add_argument("target", nargs="?", default="",
                   help="target string; omit for Drive-level listing")
p_get.add_argument("--folder", default=None, metavar="FOLDER_ID",
                   help="filter Drive listing to spreadsheets inside this folder (Drive-level only)")
add_format(p_get)
p_get.set_defaults(func=cmd_get)
```

Update `cmd_get` (around line 131):

```python
def cmd_get(args):
    client = SheetsClient()
    target = _parse_target(args.target or "")
    folder_id = getattr(args, 'folder', None)
    if folder_id is not None and classify(target) != TargetType.DRIVE:
        print("grammar error: --folder only applies to Drive-level listing (omit target)", file=sys.stderr)
        sys.exit(2)
    response = verbs.do_get(client, target, folder_id=folder_id)
    _emit_get(target, response, args.format == "json")
```

`TargetType` is already imported at the top of `cli.py` — no import changes needed.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest test/test_cli.py::test_get_folder_flag_forwarded_to_list_spreadsheets test/test_cli.py::test_get_folder_with_non_drive_target_exits_error -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/sheet_cli/cli.py test/test_cli.py
git commit -m "feat: add --folder flag to CLI get command"
```

---

### Task 4: Expose `folder_id` in MCP `sheets_get`

**Files:**
- Modify: `mcp-server/sheet-service.py`
- Test: `mcp-server/test_server.py`

- [ ] **Step 1: Write the failing tests**

The existing `test_server.py` uses subprocess + JSON-RPC. Add two tests using the same `send_request` helper and server process pattern already in that file. Insert after the existing `test_mcp_server` function:

```python
def test_sheets_get_folder_id_accepted():
    """sheets_get with folder_id in args must not return an error for empty target."""
    process = subprocess.Popen(
        [VENV_PYTHON, SERVER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
    )
    try:
        send_request(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        resp = send_request(process, {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "sheets_get",
                "arguments": {"target": "", "folder_id": "FAKEFOLDER"}
            }
        })
        # Will fail with AuthenticationError (no token in CI), not a grammar error
        if "error" in resp:
            assert "grammar" not in resp["error"]["message"].lower(), \
                f"Got unexpected grammar error: {resp['error']['message']}"
    finally:
        process.stdin.close()
        process.wait(timeout=5)


def test_sheets_get_folder_id_with_non_drive_target_returns_grammar_error():
    """sheets_get with folder_id + non-empty target must return a grammar error."""
    process = subprocess.Popen(
        [VENV_PYTHON, SERVER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
    )
    try:
        send_request(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        resp = send_request(process, {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "sheets_get",
                "arguments": {"target": "SOMESID:Sheet1", "folder_id": "FOLDER123"}
            }
        })
        assert "error" in resp
        assert "folder_id" in resp["error"]["message"]
    finally:
        process.stdin.close()
        process.wait(timeout=5)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
venv/bin/pytest mcp-server/test_server.py::test_sheets_get_folder_id_accepted mcp-server/test_server.py::test_sheets_get_folder_id_with_non_drive_target_returns_grammar_error -v
```

Expected: second test `FAILED` — no grammar error is returned for non-DRIVE target + `folder_id`.

- [ ] **Step 3: Update MCP `sheets_get` tool definition and dispatch**

**3a.** In `mcp-server/sheet-service.py`, check the `from sheet_cli.grammar import (...)` block at the top. Add `TargetType` and `classify` if missing:

```python
from sheet_cli.grammar import (
    GrammarError,
    Target,
    TargetType,
    classify,
    parse,
    resolve,
)
```

**3b.** In `get_tools()`, add `folder_id` to `sheets_get` `inputSchema` properties (after the `format` property):

```python
"folder_id": {
    "type": "string",
    "description": "Drive folder ID. Only valid when target is empty (Drive-level listing). Filters to spreadsheets directly inside this folder.",
},
```

**3c.** In `sheets_get` description, add to the `TARGET SHAPES` block:

```
- '' + folder_id      → spreadsheets directly inside a specific Drive folder
```

**3d.** Update the `execute_tool` dispatch for `sheets_get` (around line 339):

```python
if name == "sheets_get":
    target = _parse_first(args.get("target", ""))
    folder_id = args.get("folder_id")
    if folder_id is not None and classify(target) != TargetType.DRIVE:
        raise GrammarError("folder_id only applies to Drive-level listing (omit target or pass empty string)")
    response = verbs.do_get(self.client, target, folder_id=folder_id)
    if args.get("format") == "text":
        return _format_as_text(target, response)
    return response
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
venv/bin/pytest mcp-server/test_server.py::test_sheets_get_folder_id_accepted mcp-server/test_server.py::test_sheets_get_folder_id_with_non_drive_target_returns_grammar_error -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Run the full test suite**

```bash
venv/bin/pytest test/ mcp-server/test_server.py -v
```

Expected: all tests `PASSED`. No regressions.

- [ ] **Step 6: Commit**

```bash
git add mcp-server/sheet-service.py mcp-server/test_server.py
git commit -m "feat: expose folder_id in MCP sheets_get tool"
```
