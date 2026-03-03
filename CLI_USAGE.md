# CLI Usage Guide

Quick reference for using the `sheet-cli` command-line tool.

## Installation

```bash
# From project root
venv/bin/pip install -e .
```

## Authentication Setup

1. **Get OAuth credentials** (one-time setup):
   - Visit [Google Cloud Console](https://console.cloud.google.com)
   - Create/select a project
   - Enable Google Sheets API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download as `~/.sheet-cli/credentials.json`

2. **Enable APIs** in Google Cloud Console: Google Sheets API and Google Drive API

3. **First authentication** (opens browser once):
```bash
venv/bin/sheet-cli auth
```
   - Browser opens for Google sign-in
   - Grant access to sheets and Drive metadata
   - Token cached in `~/.sheet-cli/token.pickle`
   - Credentials stored with secure permissions (directory: 700, files: 600)
   - Re-run `auth` any time to switch accounts or force re-authentication

## Command Reference

### 1. auth - Authenticate

```bash
venv/bin/sheet-cli auth
```

Forces a fresh OAuth flow. Use on first setup, to switch accounts, or when authentication breaks.

### 2. list - List Spreadsheets

```bash
# Text table: ID, modified date, name
venv/bin/sheet-cli list

# Include Shared Drives (team/org drives)
venv/bin/sheet-cli list --shared

# Raw JSON output
venv/bin/sheet-cli list --json
```

The ID in the first column is what you pass to all other commands.

### 3. read - Read Cell Values

Read values or formulas from cells/ranges.

**Basic usage:**
```bash
# Read entire spreadsheet (all sheets, all data)
venv/bin/sheet-cli read SHEET_ID

# Read single cell
venv/bin/sheet-cli read SHEET_ID A1

# Read multiple cells
venv/bin/sheet-cli read SHEET_ID A1 A2 B3

# Read range
venv/bin/sheet-cli read SHEET_ID A1:C10

# Read from specific sheet
venv/bin/sheet-cli read SHEET_ID Sheet1!A1:B10

# Multiple ranges
venv/bin/sheet-cli read SHEET_ID A1:A10 C1:C10 Sheet2!A1:B5
```

**Output format:**
```
A1 value1
A2 value2
B1 hello world
```

**Notes:**
- **No ranges specified**: Reads all data from all sheets in the spreadsheet
- Shows formulas (with `=` prefix) when cells contain formulas
- Empty cells are omitted from output
- Multi-range reads are supported

### 2. write - Write Cell Values

Write values or formulas to cells. Three input methods:

#### Method 1: Command-line arguments (quick writes)
```bash
# Single cell
venv/bin/sheet-cli write SHEET_ID A1 "hello world"

# Multiple cells (alternating cell/value pairs)
venv/bin/sheet-cli write SHEET_ID A1 100 A2 200 A3 "=SUM(A1:A2)"

# Formula
venv/bin/sheet-cli write SHEET_ID D1 "=AVERAGE(A1:C1)"
```

#### Method 2: Space-delimited stdin (easy for scripts)
```bash
# Each line: cell value [value ...]
echo 'A1 hello world
A2 123
A3 =SUM(A1:A2)' | venv/bin/sheet-cli write SHEET_ID

# From file
cat data.txt | venv/bin/sheet-cli write SHEET_ID
```

**Space-delimited format:**
- First token: cell reference (A1, Sheet1!B2, etc.)
- Remaining tokens: value (joined with spaces)
- Formulas: start with `=`
- Multi-word values: everything after cell is the value

#### Method 3: JSON stdin (structured data)
```bash
# Simple key-value
echo '{"A1": "hello", "A2": 123, "A3": "=SUM(A1:A2)"}' | venv/bin/sheet-cli write SHEET_ID

# Range-based (2D arrays)
echo '{
  "Sheet1!A1:B2": [
    ["Name", "Score"],
    ["Alice", 95]
  ]
}' | venv/bin/sheet-cli write SHEET_ID
```

**Output:**
```
Updated 5 cells
```

### 3. metadata - Get Spreadsheet Structure

Get complete spreadsheet metadata as JSON.

**Usage:**
```bash
venv/bin/sheet-cli meta_read SHEET_ID
```

**Output (JSON):**
```json
{
  "spreadsheetId": "...",
  "properties": {
    "title": "My Spreadsheet",
    "locale": "en_US",
    "timeZone": "America/New_York"
  },
  "sheets": [
    {
      "properties": {
        "sheetId": 0,
        "title": "Sheet1",
        "index": 0,
        "gridProperties": {
          "rowCount": 1000,
          "columnCount": 26
        }
      }
    }
  ]
}
```

**Use cases:**
- Find sheet IDs (needed for structure operations)
- List all sheet names
- Check spreadsheet properties
- Get grid dimensions

### 4. structure - Modify Spreadsheet Structure

Execute batch update operations (formatting, sheets, etc.) from JSON.

**Usage:**
```bash
# From stdin
echo '{"requests": [...]}' | venv/bin/sheet-cli meta_write SHEET_ID

# From file
cat operations.json | venv/bin/sheet-cli meta_write SHEET_ID
```

**JSON format:**
```json
{
  "requests": [
    {
      "addSheet": {
        "properties": {
          "title": "New Sheet"
        }
      }
    }
  ]
}
```

Or just an array:
```json
[
  {"addSheet": {"properties": {"title": "New Sheet"}}}
]
```

## Common Workflows

### Example 1: Read and Process Data
```bash
# Read entire spreadsheet and search for a value
venv/bin/sheet-cli read SHEET_ID | grep "TODO"

# Read specific range and process
venv/bin/sheet-cli read SHEET_ID A1:A10 | grep "TODO" > tasks.txt

# Find all formulas in spreadsheet
venv/bin/sheet-cli read SHEET_ID | grep "^[^!]*!.*=" | head
```

### Example 2: Bulk Data Import
```bash
# Generate data and write to sheet
for i in {1..10}; do
  echo "A$i Value $i"
done | venv/bin/sheet-cli write SHEET_ID
```

### Example 3: Create Formatted Sheet
```bash
# Step 1: Get sheet ID
venv/bin/sheet-cli meta_read SHEET_ID | jq '.sheets[0].properties.sheetId'

# Step 2: Write header row
venv/bin/sheet-cli write SHEET_ID A1 Name B1 Score C1 Grade

# Step 3: Format header (bold, gray background)
echo '{
  "requests": [
    {
      "repeatCell": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 0,
          "endRowIndex": 1
        },
        "cell": {
          "userEnteredFormat": {
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "textFormat": {"bold": true}
          }
        },
        "fields": "userEnteredFormat"
      }
    }
  ]
}' | venv/bin/sheet-cli meta_write SHEET_ID
```

### Example 4: Copy Data Between Sheets
```bash
# Copy between tabs in the same spreadsheet
venv/bin/sheet-cli copy SHEET_ID Sheet1!A1:C10 Archive!A1

# Copy to a different spreadsheet
venv/bin/sheet-cli copy SOURCE_ID Sheet1!A1:C10 DEST_ID Sheet2!A1

# Copy values only (flatten formulas)
venv/bin/sheet-cli copy SHEET_ID Sheet1!A1:C10 Sheet2!A1 --value
```

## Tips

1. **Spreadsheet ID**: Found in URL between `/d/` and `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/1abc...xyz/edit
                                          ^^^^^^^^^
   ```

2. **Formulas**: Always start with `=`
   - Write: `venv/bin/sheet-cli write SHEET_ID A1 "=SUM(B:B)"`
   - Read: Shows formula as written

3. **Ranges**: Support multiple formats:
   - `A1` - Single cell
   - `A1:B10` - Range
   - `Sheet1!A1:B10` - Specific sheet
   - `A:A` - Entire column
   - `1:1` - Entire row

4. **Piping**: All commands work with Unix pipes
   ```bash
   venv/bin/sheet-cli read SHEET_ID A:A | sort | uniq
   ```

5. **Error handling**: Check exit code
   ```bash
   if venv/bin/sheet-cli read SHEET_ID A1; then
     echo "Success"
   else
     echo "Failed"
   fi
   ```

## Troubleshooting

### "Credentials file not found"
- Run `sheet-cli auth` for step-by-step setup instructions
- Ensure `~/.sheet-cli/credentials.json` is a Desktop app OAuth 2.0 Client ID JSON

### "Token expired" / "Invalid credentials"
- Run `sheet-cli auth` to re-authenticate

### "Permission denied"
- Ensure your Google account has access to the spreadsheet
- Check OAuth scopes include sheets access

### "Invalid range"
- Verify sheet name exists
- Check A1 notation format
- Sheet names with spaces: use quotes in shell

## See Also

- API Reference: `API.md`
- Library usage: `CLAUDE.md`
- MCP Server: `mcp-server/README.md`
- Google Sheets API: https://developers.google.com/sheets/api
