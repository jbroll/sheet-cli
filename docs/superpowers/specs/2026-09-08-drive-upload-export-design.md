# drive-cli upload / export

Two new verbs on `drive-cli`: `upload` puts a local file into Drive, `export`
pulls a Drive file back out as a local file. Both guess mimeTypes from the file
extension, with flags to override.

## Why

`drive-cli` can copy, move and create, but it cannot get bytes in or out. Putting
a locally generated `.docx` into Drive as a Google Doc, or pulling a Doc back
down as a PDF, currently means writing a one-off script against
`google-api-python-client` using the cached token.

## Scope

Drive API only: `files.create`, `files.update`, `files.export`, `files.get`.
Nothing calls the Docs API, so there is no `docs-cli` and no third binary.

The cached token's existing `https://www.googleapis.com/auth/drive` scope covers
all four calls. No re-auth, no change to `SCOPES` in `sheet_client/auth.py`.

MCP tools are not registered for these verbs. `do_upload` and `do_export` live in
`ops.py` alongside the other verb cores, so the MCP server can pick them up
later.

## Command surface

```
drive-cli upload FILE [ID] [--name NAME] [--raw | --to doc|sheet|slides]
                           [--mime TYPE]
drive-cli export ID FILE [--mime TYPE]
```

`upload` follows the trailing-optional-positional pattern of `copy ID [FOLDER]`
and `new kind NAME [FOLDER]`. The optional `ID` is resolved by mimeType exactly
as `do_copy` already resolves its source:

| `ID` | Behavior |
|---|---|
| omitted | create in My Drive root |
| a folder | create inside that folder |
| anything else | replace that file's bytes, keeping ID, URL, sharing, comments |

Replacing is `files.update` with a media body. The file keeps its identity, so a
published link keeps working and Drive records a new revision.

```bash
drive-cli upload flyer.docx              # -> Google Doc in root
drive-cli upload flyer.docx FOLDERID     # -> Google Doc in a folder
drive-cli upload flyer.docx DOCID        # -> replaces that Doc, same URL
drive-cli upload flyer.docx --raw        # -> stored as .docx, no conversion
drive-cli upload notes.txt --to doc      # -> force a Doc
drive-cli upload data --mime text/csv    # -> extension missing, state it

drive-cli export DOCID out.pdf           # -> application/pdf
drive-cli export DOCID out.docx          # -> wordprocessingml
drive-cli export SID   out.csv           # -> text/csv
drive-cli export PDFID out.pdf           # -> raw download, not an export
```

## `src/drive_cli/mimes.py`

A data module with no imports from `sheet_client` or `googleapiclient`, so it is
testable offline. Three tables and three functions.

```
EXT_TO_MIME      extension -> source mimeType
MIME_TO_NATIVE   source mimeType -> google-apps type (absent = no conversion)
NATIVE_EXPORTS   google-apps type -> {extension: export mimeType}
```

- `source_mime(path) -> str | None` — from the extension, `None` if unknown.
- `native_target(source_mime) -> str | None` — the Google-native type to convert
  to, `None` when there is no equivalent.
- `export_mime(file_mime, out_path) -> str` — the export mimeType for a native
  file written to that extension.

Coverage:

| Extensions | Source type | Converts to |
|---|---|---|
| `.docx .doc .odt .rtf .txt .html .htm .md` | word processing | Doc |
| `.xlsx .xls .csv .tsv .ods` | spreadsheet | Sheet |
| `.pptx .ppt .odp` | presentation | Slides |
| `.pdf .png .jpg .jpeg .gif .svg .zip .json` | other | nothing, raw |

Export targets:

| Native type | Extensions |
|---|---|
| Doc | `pdf docx odt rtf txt html epub` |
| Sheet | `pdf xlsx ods csv tsv zip` |
| Slides | `pdf pptx odp txt` |

## `ops.do_upload`

```python
do_upload(client, path, target=None, *, raw=False, to=None,
          name=None, mime=None) -> dict
```

1. Source mimeType: `mime` if given, else `source_mime(path)`. Neither means an
   error naming `--mime`.
2. Destination: `target` absent means create at root. Otherwise one
   `client.get_file_mime(target)` call decides create-in-folder vs. replace.
3. Conversion target: `None` under `raw`; the type `to` names under `--to`;
   otherwise `native_target(source)`.
4. Create is `client.upload_file(...)`, replace is
   `client.update_file_content(...)`.
5. Returns `{"action": "created"|"replaced", "id", "name", "mimeType",
   "webViewLink"}`.

`--raw` and `--to` are mutually exclusive. On the replace branch the existing
file's type already fixes the stored format, so `--to` naming a different type is
an error rather than a silent no-op.

Default `name` is the basename of `path` with its extension stripped when
converting, and the full basename when not. Replacing leaves the existing name
alone unless `--name` is given.

## `ops.do_export`

```python
do_export(client, file_id, out_path, *, mime=None) -> dict
```

`client.get_file_mime(file_id)` decides the path. A `google-apps.*` type is an
export: the mimeType comes from `--mime`, else `export_mime(file_mime,
out_path)`. Any other type has nothing to convert, so it is a plain media
download and `--mime` on it is an error.

Returns `{"id", "name", "mimeType", "exported_as", "path", "bytes"}`.

Drive refuses to export a document over 10MB. That 403 is caught and re-raised
saying so, pointing at downloading a `.pdf` from the Drive UI instead.

## Client methods

Three thin wrappers in `sheet_client/client.py`, next to `copy_file`, keeping
`googleapiclient` imports out of `ops.py`:

- `upload_file(path, source_mime, *, name, convert_to=None, parent_folder_id=None)`
- `update_file_content(file_id, path, source_mime, *, name=None)`
- `export_file(file_id, out_path, export_mime=None)`

All three go through `_execute_with_retry`, so 429/500/503 back off like every
other call. Uploads pass `resumable=True`, which covers files past Drive's 5MB
simple-upload limit without a separate code path. Downloads use
`MediaIoBaseDownload` in chunks so a large export does not have to fit in memory
at once.

## Errors

| Condition | Exit | Message |
|---|---|---|
| `FILE` does not exist | 2 | path, from the `ValueError` handler in `main()` |
| unknown extension, no `--mime` | 2 | names `--mime` |
| `--raw` with `--to` | 2 | mutually exclusive |
| `--to` disagreeing with the file being replaced | 2 | names the existing type |
| export extension not valid for the type | 2 | lists the valid extensions |
| `--mime` on a non-native export | 2 | says the file needs no conversion |
| export over 10MB | 1 | Drive's limit |

## Tests

`test/test_mimes.py`, offline: extension mapping including unknown and
extensionless paths, native target selection, export mimeType selection, and the
error cases for both.

`test/test_drive_ops.py`, new classes on the existing `MagicMock` client fixture:
create at root, create in a folder, replace a file, `--raw`, `--to`, the
`--to`-disagrees error, export of each native type, raw media download, and
`--mime` rejected on a non-native file.

`test/test_drive_cli.py`: parsing for both verbs, including the mutually
exclusive flags.

No integration tests against real Drive.

## Docs

Same commit: the `drive-cli` sections of `README.md` and `CLAUDE.md`, and
`API.md` for the three new client methods.

## Not doing

- No `docs-cli`, and no Docs API call of any kind.
- No MCP tools.
- No recursive folder upload. `upload` takes one file.
- No sync or change detection. Replacing always sends the whole file.
