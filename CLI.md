# CLI Reference

Command-line interface for Google Sheets API v4. Provides direct access to read, write, structure, and metadata operations.

## Installation

```bash
# Install in virtual environment
python3 -m venv venv
venv/bin/pip install -e .

# CLI available as
venv/bin/sheet-cli
```

## Commands

The CLI provides four commands that map directly to the library API:

```bash
sheet-cli read       # Read cell values
sheet-cli write      # Write cell values
sheet-cli meta_write  # Batch structure operations
sheet-cli meta_read   # Get spreadsheet metadata
```

## Authentication

First run initiates OAuth flow. Browser opens for authorization. Token cached to `~/.sheet-cli/token.pickle` for subsequent runs.

Required files (stored in `~/.sheet-cli/`):
- `~/.sheet-cli/credentials.json` - OAuth 2.0 Client ID from Google Cloud Console
- `~/.sheet-cli/token.pickle` - Auto-generated after first auth

**Security**: Credentials stored with secure permissions (directory: 700, files: 600)

## Data Formats

### Space-Delimited Format

Primary format for cell/value pairs:

```
cell value
cell value
cell =formula
```

**Rules:**
- Split on first space only
- Everything after first space is the value
- Formulas indicated by leading `=`
- Multi-word values supported
- Sheet names supported: `Sheet2!A1 value`

**Examples:**
```
A1 hello world
A2 123
A3 =SUM(A1:A2)
Sheet2!B5 multi word value
B1 =IF(A1="hello", "yes", "no")
```

### JSON Format

Alternative format for structured data:

```json
{
  "A1": "hello",
  "A2": 123,
  "A3": "=SUM(A1:A2)"
}
```

Or for ranges:
```json
{
  "A1:B2": [["a1", "b1"], ["a2", "b2"]]
}
```

**Auto-detection:** CLI detects format automatically (JSON starts with `{` or `[`).

---

## read

Read values from specified cells or ranges.

### Syntax

```bash
sheet-cli read SPREADSHEET_ID RANGE [RANGE ...]
```

### Arguments

- `SPREADSHEET_ID` - Spreadsheet ID from URL
- `RANGE` - One or more cell/range addresses in A1 notation

### Output

Space-delimited cell/value pairs to stdout:

```
cell value
cell value
cell =formula
```

### Examples

**Single cell:**
```bash
sheet-cli read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms A1
```

**Multiple cells:**
```bash
sheet-cli read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms A1 A2 B1
```

**Ranges:**
```bash
sheet-cli read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms A1:A10 B1:B10
```

**Multiple sheets:**
```bash
sheet-cli read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms Sheet1!A1:C10 Sheet2!A1:C10
```

**Output example:**
```
A1 Product
A2 Widget
A3 Gadget
B1 Price
B2 10.99
B3 =A2*1.1
```

### Formulas

Formulas are returned with leading `=`:
```bash
sheet-cli read SHEET_ID D1:D10
# Output:
# D1 =SUM(A1:C1)
# D2 =SUM(A2:C2)
```

---

## write

Write values to cells from command line or stdin.

### Syntax

**From command line:**
```bash
sheet-cli write SPREADSHEET_ID CELL VALUE [CELL VALUE ...]
```

**From stdin:**
```bash
sheet-cli write SPREADSHEET_ID < input.txt
cat data.txt | sheet-cli write SPREADSHEET_ID
```

### Arguments

- `SPREADSHEET_ID` - Spreadsheet ID from URL
- `CELL VALUE` - Alternating cell address and value pairs (optional)

### Input Formats

**Command line (alternating pairs):**
```bash
sheet-cli write SHEET_ID A1 "hello" A2 123 A3 "=SUM(A1:A2)"
```

**Stdin - Space-delimited:**
```bash
echo 'A1 hello world
A2 123
A3 =SUM(A1:A2)' | sheet-cli write SHEET_ID
```

**Stdin - JSON:**
```bash
echo '{"A1": "hello", "A2": 123, "A3": "=SUM(A1:A2)"}' | sheet-cli write SHEET_ID
```

### Output

Summary to stderr:
```
Updated 3 cells
```

### Examples

**Write single cell:**
```bash
sheet-cli write 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms A1 "Hello"
```

**Write multiple cells:**
```bash
sheet-cli write SHEET_ID A1 "Name" B1 "Age" C1 "Email"
```

**Write formulas:**
```bash
sheet-cli write SHEET_ID D1 "=SUM(A:A)" E1 "=AVERAGE(B:B)"
```

**Multi-word values:**
```bash
sheet-cli write SHEET_ID A1 "hello world" A2 "foo bar baz"
```

**From file:**
```bash
cat << EOF | sheet-cli write SHEET_ID
A1 Product Name
A2 Widget Pro
A3 Gadget Plus
B1 Price
B2 19.99
B3 29.99
C1 Total
C2 =B2*1.1
C3 =B3*1.1
EOF
```

**From JSON file:**
```bash
cat data.json | sheet-cli write SHEET_ID
# Where data.json contains:
# {"A1": "hello", "A2": 123, "A3": "=SUM(A1:A2)"}
```

**Different sheets:**
```bash
sheet-cli write SHEET_ID Sheet1!A1 "Data1" Sheet2!A1 "Data2"
```

### Formulas

Formulas must start with `=`:
```bash
# Correct
sheet-cli write SHEET_ID A1 "=SUM(B:B)"

# Incorrect (treated as text)
sheet-cli write SHEET_ID A1 "SUM(B:B)"
```

---

## structure

Execute batch structure operations from JSON stdin.

### Syntax

```bash
sheet-cli meta_write SPREADSHEET_ID < requests.json
echo '{"requests": [...]}' | sheet-cli meta_write SPREADSHEET_ID
```

### Arguments

- `SPREADSHEET_ID` - Spreadsheet ID from URL

### Input Format

JSON with `requests` array or array of requests:

```json
{
  "requests": [
    {"addSheet": {...}},
    {"updateSheetProperties": {...}},
    {"repeatCell": {...}}
  ]
}
```

Or just the array:
```json
[
  {"addSheet": {...}},
  {"updateSheetProperties": {...}}
]
```

### Output

Raw API response as JSON to stdout.

### Examples

**Add new sheet:**
```bash
echo '{
  "requests": [{
    "addSheet": {
      "properties": {
        "title": "Sales Data",
        "gridProperties": {
          "rowCount": 100,
          "columnCount": 10
        }
      }
    }
  }]
}' | sheet-cli meta_write SHEET_ID
```

**Freeze header row:**
```bash
echo '{
  "requests": [{
    "updateSheetProperties": {
      "properties": {
        "sheetId": 0,
        "gridProperties": {
          "frozenRowCount": 1
        }
      },
      "fields": "gridProperties.frozenRowCount"
    }
  }]
}' | sheet-cli meta_write SHEET_ID
```

**Format header:**
```bash
echo '{
  "requests": [{
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
      "fields": "userEnteredFormat(backgroundColor,textFormat)"
    }
  }]
}' | sheet-cli meta_write SHEET_ID
```

**Multiple operations:**
```bash
cat << 'EOF' | sheet-cli meta_write SHEET_ID
{
  "requests": [
    {"addSheet": {"properties": {"title": "Dashboard"}}},
    {"updateSheetProperties": {
      "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
      "fields": "gridProperties.frozenRowCount"
    }},
    {"autoResizeDimensions": {
      "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 5}
    }}
  ]
}
EOF
```

### Request Types

Common request types (see [Google Sheets API docs](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request)):

- `addSheet` - Create new sheet
- `deleteSheet` - Remove sheet
- `updateSheetProperties` - Modify sheet properties
- `repeatCell` - Apply formatting to range
- `updateCells` - Update cell values/formats
- `mergeCells` - Merge cell range
- `autoResizeDimensions` - Auto-fit columns/rows
- `insertDimension` - Insert rows/columns
- `deleteDimension` - Delete rows/columns
- `addConditionalFormatRule` - Add conditional formatting
- `addProtectedRange` - Protect cells

---

## metadata

Get spreadsheet metadata and structure.

### Syntax

```bash
sheet-cli meta_read SPREADSHEET_ID
```

### Arguments

- `SPREADSHEET_ID` - Spreadsheet ID from URL

### Output

Complete metadata as JSON to stdout:

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
  ],
  "namedRanges": [...]
}
```

### Examples

**Get all metadata:**
```bash
sheet-cli meta_read 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
```

**Extract sheet names:**
```bash
sheet-cli meta_read SHEET_ID | jq -r '.sheets[].properties.title'
```

**Get sheet IDs:**
```bash
sheet-cli meta_read SHEET_ID | jq -r '.sheets[] | "\(.properties.title): \(.properties.sheetId)"'
```

**Find named ranges:**
```bash
sheet-cli meta_read SHEET_ID | jq '.namedRanges'
```

**Pretty print:**
```bash
sheet-cli meta_read SHEET_ID | jq '.'
```

---

## Common Workflows

### Read and process data

```bash
# Read data, process with awk, save to file
sheet-cli read SHEET_ID A1:A100 | awk '{print $2}' > values.txt

# Read and filter
sheet-cli read SHEET_ID A1:B100 | grep "Important"

# Count non-empty cells
sheet-cli read SHEET_ID A1:A100 | wc -l
```

### Generate and write data

```bash
# Generate sequence
for i in {1..10}; do echo "A$i $i"; done | sheet-cli write SHEET_ID

# From CSV (convert to space-delimited)
cat data.csv | awk -F',' '{print "A"NR, $1}' | sheet-cli write SHEET_ID

# Timestamp data
echo "A1 $(date)" | sheet-cli write SHEET_ID
```

### Copy data between sheets

```bash
# Read from one sheet, write to another
sheet-cli read SOURCE_SHEET A1:C10 | sheet-cli write DEST_SHEET
```

### Backup data

```bash
# Save all data to file
sheet-cli read SHEET_ID A1:Z1000 > backup.txt

# Restore from backup
cat backup.txt | sheet-cli write SHEET_ID
```

### Complex updates

```bash
# Read, transform, write back
sheet-cli read SHEET_ID A1:A10 | \
  awk '{print $1, toupper($2)}' | \
  sheet-cli write SHEET_ID
```

### Batch formatting

```bash
# Create formatted table
cat << 'EOF' | sheet-cli meta_write SHEET_ID
{
  "requests": [
    {"repeatCell": {
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
      "cell": {
        "userEnteredFormat": {
          "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
          "textFormat": {"bold": true, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        }
      },
      "fields": "userEnteredFormat"
    }},
    {"updateSheetProperties": {
      "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
      "fields": "gridProperties.frozenRowCount"
    }},
    {"autoResizeDimensions": {
      "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 10}
    }}
  ]
}
EOF
```

---

## Error Handling

### Authentication Errors

```bash
# Missing credentials.json
Error: [Errno 2] No such file or directory: '~/.sheet-cli/credentials.json'
# Solution: Download OAuth credentials from Google Cloud Console
mkdir -p ~/.sheet-cli && chmod 700 ~/.sheet-cli
# Place credentials.json in ~/.sheet-cli/

# Expired/invalid token
# Solution: Delete token.pickle and re-authenticate
rm ~/.sheet-cli/token.pickle
sheet-cli read SHEET_ID A1
```

### Invalid Input

```bash
# Odd number of args for write
sheet-cli write SHEET_ID A1 "value" A2
# Error: Must provide alternating cell/range and value pairs

# Invalid range
sheet-cli read SHEET_ID XYZ123
# Error: API error 400: Invalid range
```

### No Input

```bash
# Write with no stdin or args
sheet-cli write SHEET_ID
# Error: No input provided. Use command line args or pipe data to stdin.

# Structure with no stdin
sheet-cli meta_write SHEET_ID
# Error: No input provided. Pipe JSON to stdin.
```

---

## Tips

### Use environment variable for spreadsheet ID

```bash
export SHEET_ID="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
sheet-cli read $SHEET_ID A1:A10
```

### Combine with jq for JSON processing

```bash
# Read metadata and extract specific fields
sheet-cli meta_read $SHEET_ID | jq '.sheets[0].properties'

# Build structure requests with jq
jq -n '{"requests": [{"addSheet": {"properties": {"title": "NewSheet"}}}]}' | \
  sheet-cli meta_write $SHEET_ID
```

### Use heredocs for multi-line input

```bash
cat << 'EOF' | sheet-cli write SHEET_ID
A1 Name
A2 Alice
A3 Bob
B1 Score
B2 95
B3 87
C1 Grade
C2 =IF(B2>=90,"A","B")
C3 =IF(B3>=90,"A","B")
EOF
```

### Shell functions for convenience

```bash
# Add to ~/.bashrc
read_sheet() {
  sheet-cli read "$SHEET_ID" "$@"
}

write_sheet() {
  sheet-cli write "$SHEET_ID" "$@"
}

# Usage
read_sheet A1:A10
echo "A1 hello" | write_sheet
```

---

## Comparison: Command Line vs Stdin

### write command

**Command line:** Best for quick updates
```bash
sheet-cli write SHEET_ID A1 "hello" A2 "world"
```

**stdin:** Best for bulk data
```bash
cat data.txt | sheet-cli write SHEET_ID
```

**When to use each:**
- Command line: 1-5 cell updates
- stdin: Bulk updates, generated data, file imports

---

## See Also

- **API.md** - Complete library API reference
- **CLAUDE.md** - Claude Code usage patterns
- **README.md** - Installation and overview
- **Google Sheets API v4** - https://developers.google.com/sheets/api
