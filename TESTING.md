# Testing Guide

## Refactoring Status ✅

The SheetsClient has been successfully refactored to support:
- **Optional `spreadsheet_id` parameter** in all methods (read, write, metadata, structure)
- **Backward compatibility** - existing code still works
- **MCP-ready** - can handle multiple spreadsheets via parameters

### What Changed

**Before:**
```python
client = SheetsClient(spreadsheet_id='ABC123')  # Fixed at init
client.read(['A1:B10'])  # Uses ABC123
```

**After (both patterns work):**
```python
# Pattern 1: Backward compatible (existing code)
client = SheetsClient(spreadsheet_id='ABC123')
client.read(['A1:B10'])  # Uses ABC123

# Pattern 2: New MCP pattern
client = SheetsClient()  # No default
client.read(['A1:B10'], spreadsheet_id='ABC123')  # Per-call
client.read(['C1:D10'], spreadsheet_id='XYZ789')  # Different sheet!
```

## Running Tests

### Unit Tests (No Credentials Required) ✅

Run all unit tests to verify the refactoring:

```bash
venv/bin/python -m pytest test/ -v --ignore=test/test_integration.py
```

**Status:** ✅ All 33 tests passing

Tests cover:
- Utility functions (A1 notation, column conversion)
- Spreadsheet ID parameter handling
- All 4 core methods (read, write, metadata, structure)
- Backward compatibility
- Error handling

### Integration Tests (Requires OAuth Setup)

Integration tests verify OAuth flow and real API calls.

#### Prerequisites

1. **Google Cloud Project Setup**
   - Create a project at https://console.cloud.google.com
   - Enable Google Sheets API
   - Create OAuth 2.0 Client ID (Desktop application)
   - Download as `~/.sheet-cli/credentials.json`
   - Create directory: `mkdir -p ~/.sheet-cli && chmod 700 ~/.sheet-cli`

2. **Test Spreadsheet**
   - Create a test Google Spreadsheet
   - Note the spreadsheet ID from the URL:
     ```
     https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit
     ```

#### Running Integration Tests

```bash
# Set your test spreadsheet ID
export SHEETS_TEST_SPREADSHEET_ID="your-spreadsheet-id-here"

# Run integration tests
venv/bin/python -m pytest test/test_integration.py -v -s
```

**First run:**
- Browser will open for OAuth authorization
- Grant access to your Google account
- `~/.sheet-cli/token.pickle` file will be created with secure permissions
- Tests will run

**Subsequent runs:**
- Cached token is used (no browser)
- Tests run immediately

#### What Integration Tests Cover

1. **OAuth Flow**
   - Verifies authentication works
   - Checks token caching

2. **Basic Operations**
   - Read/write with instance default spreadsheet_id
   - Read/write with parameter spreadsheet_id
   - Metadata operations
   - Formula handling

3. **Multiple Spreadsheets**
   - Demonstrates MCP pattern: one client, many sheets

4. **Structure Operations**
   - Getting sheet IDs
   - Preparing for formatting operations

5. **Error Handling**
   - Missing spreadsheet_id
   - Invalid spreadsheet_id

6. **Backward Compatibility**
   - Old code patterns still work

## OAuth Flow Testing

### Manual OAuth Test

To manually test the OAuth flow:

```bash
# Make sure credentials.json exists
ls ~/.sheet-cli/credentials.json

# Run a simple metadata fetch (triggers OAuth if needed)
venv/bin/python -c "
from src.sheet_client import SheetsClient
client = SheetsClient()  # Uses ~/.sheet-cli/ by default
meta = client.meta_read('YOUR_SPREADSHEET_ID')
print(f'Spreadsheet title: {meta[\"properties\"][\"title\"]}')
print('OAuth test successful!')
"
```

**Expected behavior:**
1. **First run:** Browser opens → OAuth consent → token cached
2. **Subsequent runs:** Uses cached token → no browser

### Token Management

```bash
# View cached token
ls -la ~/.sheet-cli/token.pickle

# Force re-authentication (delete token)
rm ~/.sheet-cli/token.pickle

# Next run will trigger OAuth flow again
```

## CLI Backward Compatibility

Verify the CLI still works with the refactored client:

```bash
# Test metadata command
venv/bin/sheet-cli meta_read YOUR_SPREADSHEET_ID | head -20

# Test read command
venv/bin/sheet-cli read YOUR_SPREADSHEET_ID A1:A5

# Test write command
echo "A1 Test" | venv/bin/sheet-cli write YOUR_SPREADSHEET_ID
```

All CLI commands should work exactly as before.

## Test Summary

| Test Type | Command | Status |
|-----------|---------|--------|
| Unit Tests | `pytest test/ --ignore=test/test_integration.py` | ✅ 33 passing |
| Integration Tests | `pytest test/test_integration.py` | Requires credentials |
| OAuth Flow | Manual test with real credentials | Requires credentials |
| CLI Compatibility | Run CLI commands | Requires credentials |

## Next Steps

Once OAuth and integration tests pass:

1. ✅ Refactoring complete and tested
2. ✅ Backward compatibility verified
3. 🚀 Ready to build MCP server

The refactored client is now perfect for MCP:
- Single client instance
- Multiple spreadsheets via parameters
- OAuth works in long-running processes
- Cached authentication (fast!)

## Troubleshooting

### "No module named 'googleapiclient'"

```bash
# Make sure you're using venv python
venv/bin/python -m pytest ...

# Or activate venv
source venv/bin/activate
pytest ...
```

### "No spreadsheet_id provided"

This is expected! Means the safety check works. Provide either:
- Default in constructor: `SheetsClient(spreadsheet_id='...')`
- Parameter in method: `client.read(['A1'], spreadsheet_id='...')`

### "Authentication failed"

1. Check `~/.sheet-cli/credentials.json` exists and is valid
2. Delete `~/.sheet-cli/token.pickle` and re-authenticate
3. Verify OAuth consent screen is configured
4. Check Google Cloud project has Sheets API enabled

### Browser doesn't open for OAuth

- Check you're not in a headless environment
- OAuth requires a display and browser
- For servers, use Service Accounts (MCP will use OAuth for desktop)

## File Changes

### Modified Files
- `src/sheet_client/client.py` - Added optional spreadsheet_id parameters
- `test/test_client.py` - Fixed imports

### New Files
- `test/test_refactored_client.py` - Comprehensive unit tests (16 tests)
- `test/test_integration.py` - Integration tests with real API
- `TESTING.md` - This file

### No Breaking Changes
All existing code continues to work unchanged!
