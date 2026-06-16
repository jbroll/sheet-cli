# Drive file & folder copy — design

**Date:** 2026-06-16
**Status:** Approved, ready for implementation

## Goal

Extend the `copy` verb so it can copy **any Drive file** (not just spreadsheets)
and **whole folders recursively**, optionally placing the copy into a specific
Drive folder. Today `copy SID "Title"` already routes whole-spreadsheet copies
through Drive `files.copy`, but: (a) the result is hard-coded to spreadsheet
shape, (b) there is no way to drop the copy into a target folder from the CLI,
and (c) folders cannot be copied at all.

## Scope

In scope:
- Copy any Drive file by ID (generic `files.copy`).
- Copy a whole folder recursively.
- Place the copy in a destination folder via a new `--into FOLDER_ID` flag.
- MCP `sheets_copy` parity (`into_folder` arg).

Out of scope:
- `move --into` (moving a file between folders is already covered by the
  `.parents` property via `update_parents`).
- Copying onto Shared Drives is best-effort; not specially handled beyond what
  the API does by default.

## CLI surface

`--into FOLDER_ID` added to `copy`; the `dest` positional becomes optional.

```
copy FILE_ID                      # "Copy of <name>" in My Drive root
copy FILE_ID "New name"           # renamed copy in root
copy FILE_ID --into FOLDER_ID     # default name, placed in FOLDER_ID
copy FILE_ID "New name" --into FOLDER_ID
copy FOLDER_ID --into DEST_FOLDER # recursive folder copy
```

Rules:
- `--into` signals a **Drive whole-file/folder copy**. When present, the `dest`
  positional (if given) is the new *title* string, matching today's
  `copy SID "Title"` semantics. The source is any Drive file/folder ID.
- Folder vs file is **auto-detected at runtime via mimeType** — same syntax
  either way (consistent with the existing "dispatch picks the best API" model).
- Using `--into` together with a sheet/range-shaped `dest` (one containing `!`
  or a sheet component) is a `GrammarError`.

## Client primitives (`src/sheet_client/client.py`)

- `get_file_mime(file_id) -> str` — `files.get(fields='mimeType')`; used to
  branch file-vs-folder.
- `copy_file(source_id, new_title=None, parent_folder_id=None) -> dict` —
  generic `files.copy` returning `{id, name, mimeType, parents, url}`. `url`
  is the docs URL for Google-native types, else a generic
  `https://drive.google.com/file/d/<id>` link.
- `copy_folder(source_folder_id, new_title=None, parent_folder_id=None) -> dict`
  — the one genuinely new piece of logic:
  1. `files.create` a new folder (`mimeType
     application/vnd.google-apps.folder`, `parents=[parent_folder_id]` when set,
     `name=new_title` or `"Copy of <source name>"`).
  2. List children: `files.list(q="'<src>' in parents and trashed=false",
     fields='files(id,name,mimeType)')`, paginated via `pageToken`.
  3. For each child: folder → recurse with parent = new folder id; otherwise →
     `copy_file` into the new folder, preserving the child's name.
  4. Return `{id, name, parents, copied_files, copied_folders}` (counts are
     totals across the whole recursive tree).
- `copy_spreadsheet` is **kept unchanged** for backward compatibility.

Guards / behavior:
- Reject `parent_folder_id == source_folder_id` (copying a folder into itself)
  to avoid runaway recursion — raise `GrammarError`/`ValueError`.
- Individual child failures propagate (fail-fast); no silent skipping.

### Philosophy note

Recursive folder copy is the one "helper" in an otherwise primitive-only
library. It is justified: Drive has no recursive-copy API primitive, so
composition is the only option (exactly what the project philosophy endorses),
and it stays contained in a single method.

## Dispatch routing (`src/sheet_cli/dispatch.py`)

`do_copy` gains an `into_folder` parameter. The existing whole-spreadsheet
branch (source is a bare ID; dest is a title or bare `DRIVE`) generalizes:

- Trigger the Drive whole-file/folder path when `into_folder` is set **or** the
  dst is a title/`DRIVE` (current behavior).
- Within that path: fetch `get_file_mime(source_id)`.
  - folder mimeType → `copy_folder(source_id, new_title, parent_folder_id=into_folder)`
  - spreadsheet mimeType → `copy_spreadsheet(...)` (preserves existing
    sheet-shaped return for current callers)
  - any other mimeType → `copy_file(...)` (generic return)
- `new_title` comes from the dest positional (as today); `parent_folder_id`
  from `into_folder`.

## MCP + docs

- `sheets_copy` MCP tool: add optional `into_folder` string arg; thread it into
  `dispatch.do_copy`. Update the tool description to mention file/folder copy.
- Update `copy` help text in `cli.py`, plus `CLAUDE.md`, `API.md`, `README.md`.

## Testing (TDD)

Unit tests with a mocked `SheetsClient` / mocked `drive` service:
- CLI flag parsing: `--into` accepted; `dest` optional when `--into` present;
  `--into` + sheet-shaped dest rejected.
- Dispatch routing decisions: spreadsheet → `copy_spreadsheet`; generic file →
  `copy_file`; folder → `copy_folder`; `into_folder` threaded as
  `parent_folder_id`.
- `copy_folder` recursion: nested folder produces correct create/copy/recurse
  calls; pagination handled; self-copy guard raises; counts correct.
```
