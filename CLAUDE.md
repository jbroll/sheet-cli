# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Project Context

**Google Sheets CLI** - Minimal Python wrapper for Google Sheets REST API v4. Provides direct API access with OAuth 2.0 authentication. Approximately 300 lines of code.

**Status**: Implemented and ready for use.

## Philosophy

No opinions, just access. Direct mapping to Google's REST API with minimal abstraction.

**What this provides:**
- Discovery: Get complete spreadsheet state
- Read/Write: Direct value operations
- Batch: Full access to API batch operations
- OAuth: User authentication with token caching

**What this doesn't provide:**
- No helper functions like "create_table()"
- No theme system
- No formula parsing or analysis
- No structural analysis
- No pre-built templates

**Why**: You compose operations from raw API primitives based on user needs. No fighting with abstractions.

## Technology Stack

- Python 3.8+
- Google Sheets REST API v4 (direct)
- OAuth 2.0 (sheet owner model)
- Dependencies: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`

## File Structure

```
sheet-cli/
├── src/                  # Main package
│   ├── client.py         # SheetsClient (~250 lines)
│   ├── auth.py           # OAuth flow (~70 lines)
│   ├── utils.py          # A1 notation helpers (~90 lines)
│   ├── exceptions.py     # Custom exceptions (~30 lines)
│   └── __init__.py       # Package exports
│
├── example/              # Usage examples
├── test/                 # Unit tests
├── API.md                # Complete API reference
├── README.md             # User documentation
└── CLAUDE.md             # This file
```

## How You Use This

### Pattern 1: Always Discover First

Before making changes, get the complete state:
- Use `get_spreadsheet()` to understand structure
- Analyze raw API response to check for existing data
- Get sheet IDs needed for batch operations
- Make informed decisions based on current state

### Pattern 2: Compose Batch Operations

When user requests complex operations:
- Break into discrete API operations
- Use batch operations for formatting/structure
- Compose exactly what's needed from raw request types
- No pre-built helpers - compose fresh each time

### Pattern 3: Work with Raw API Responses

- All methods return raw Google API responses
- No parsing layers or custom data structures
- Analyze responses directly using Python
- Access any field Google provides

## Common Workflows

**Creating formatted tables:**
1. Get sheet ID from discovery
2. Write data with value operations
3. Apply formatting with batch operations
4. Use auto-resize, freeze rows, etc.

**Finding formulas:**
1. Get spreadsheet with grid data
2. Iterate through row data
3. Check cells for 'formulaValue' in 'userEnteredValue'
4. Process as needed

**Smart append vs write:**
1. Check if sheet has existing data
2. Append if data exists, write if empty
3. No magic - explicit decisions

## Implementation Notes

**Error Handling:**
- Automatic retry on 429 (rate limit) with exponential backoff
- Automatic retry on 500, 503 (server errors)
- Clear exceptions with status codes

**Authentication:**
- OAuth flow opens browser on first run
- Token cached with pickle, auto-refreshes
- User grants access to their own sheets

**Type Hints:**
- All public methods have type hints
- Return types: `dict` (raw API) or `List[List[Any]]` (values)

## API Reference

See API.md for complete technical reference including:
- All method signatures
- Request/response formats
- GridRange specifications
- A1 notation details
- Batch operation types
- Code examples

## Testing

Unit tests focus on:
- A1 notation conversion utilities
- Exception handling
- Round-trip conversions

Integration tests optional (require real spreadsheet).

## Google API Resources

When you need to compose operations, refer to:
- [spreadsheets.get](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/get)
- [spreadsheets.values](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values)
- [spreadsheets.batchUpdate](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)
- [Request types](https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request)

## Why This Design

**For you (Claude):**
- Raw API responses to analyze directly
- No abstractions to learn or work around
- Direct mapping to Google's documentation
- Compose exactly what each task needs

**For implementation:**
- Minimal code (~300 lines)
- No state management complexity
- No custom data structures
- Easy to maintain

**For users:**
- Direct API control
- Full Google Sheets API power
- No magic behavior
- Easy debugging with raw responses

## Summary

This is a thin wrapper providing authenticated access to Google Sheets REST API v4. Discovery, read, write, and batch operations. Everything else is composition.
