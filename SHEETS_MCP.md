# Google Sheets API Integration Plan for Claude Code

## Executive Summary

This document outlines a simplified, practical approach for integrating Claude Code with Google Sheets API, focusing on essential operations: reading/writing values and formulas, conditional formatting, and named ranges management.

## Core Objectives

- Read and write cell values and formulas
- Apply and modify conditional formatting
- Create and manage named ranges
- Perform batch operations efficiently
- Find and replace across spreadsheets

## Architecture Overview

### Technology Stack

- **Primary Language**: Python 3.8+
- **API**: Google Sheets API v4
- **Authentication**: Service Account with JSON credentials
- **Required Libraries**: google-api-python-client, google-auth
- **Scope**: https://www.googleapis.com/auth/spreadsheets

### Essential API Methods

1. **spreadsheets.values.get** - Read cell values or formulas
2. **spreadsheets.values.update** - Write values or formulas
3. **spreadsheets.batchUpdate** - Multiple operations, formatting, named ranges
4. **spreadsheets.get** - Retrieve spreadsheet metadata

## Implementation Guide

### Phase 1: Google Cloud Setup

#### Step 1.1: Create Google Cloud Project
- Navigate to https://console.cloud.google.com
- Click "Create Project"
- Name: "claude-sheets-integration"
- Note the Project ID for later reference

#### Step 1.2: Enable APIs
- In Google Cloud Console, go to "APIs & Services" > "Library"
- Search for "Google Sheets API"
- Click and enable the API
- No need for Drive API for basic operations

#### Step 1.3: Create Service Account
- Go to "APIs & Services" > "Credentials"
- Click "Create Credentials" > "Service Account"
- Name: "claude-code-sheets"
- Role: "Editor" (or create custom role with sheets permissions)
- Click "Done"

#### Step 1.4: Generate Credentials
- Click on the created service account
- Go to "Keys" tab
- Click "Add Key" > "Create New Key"
- Choose JSON format
- Save the downloaded file as "credentials.json"

#### Step 1.5: Share Spreadsheet
- Open your Google Sheet
- Click Share button
- Add the service account email (found in credentials.json)
- Give "Editor" permissions

### Phase 2: Local Environment Setup

#### Step 2.1: Directory Structure

    claude-sheets/
    ├── credentials.json
    ├── sheets_api.py
    ├── requirements.txt
    └── examples/
        ├── read_examples.py
        ├── write_examples.py
        └── format_examples.py

#### Step 2.2: Install Dependencies

Create requirements.txt:

    google-api-python-client==2.100.0
    google-auth==2.23.0
    google-auth-oauthlib==1.1.0
    google-auth-httplib2==0.1.1

Install command:

    pip install -r requirements.txt

### Phase 3: Core Implementation

#### Step 3.1: Main API Class (sheets_api.py)

    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from typing import List, Dict, Any, Optional

    class GoogleSheetsAPI:
        """Simplified Google Sheets API interface for Claude Code"""
        
        def __init__(self, credentials_path: str, spreadsheet_id: str):
            """
            Initialize the Google Sheets API client
            
            Args:
                credentials_path: Path to service account JSON file
                spreadsheet_id: ID of the target spreadsheet
            """
            self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            self.creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.creds)
            self.spreadsheet_id = spreadsheet_id
            self.sheets = self.service.spreadsheets()
        
        # === CORE READING FUNCTIONS ===
        
        def read_values(self, range_name: str) -> List[List[Any]]:
            """Read cell values from specified range"""
            result = self.sheets.values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            return result.get('values', [])
        
        def read_formulas(self, range_name: str) -> List[List[str]]:
            """Read formulas as strings from specified range"""
            result = self.sheets.values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueRenderOption='FORMULA'
            ).execute()
            return result.get('values', [])
        
        def read_with_formatting(self, range_name: str) -> Dict[str, Any]:
            """Read values with their formatting information"""
            result = self.sheets.get(
                spreadsheetId=self.spreadsheet_id,
                ranges=[range_name],
                includeGridData=True
            ).execute()
            return result
        
        # === CORE WRITING FUNCTIONS ===
        
        def write_values(self, range_name: str, values: List[List[Any]], 
                        input_option: str = 'USER_ENTERED') -> Dict[str, Any]:
            """
            Write values or formulas to specified range
            
            Args:
                range_name: A1 notation range
                values: 2D array of values to write
                input_option: 'RAW' or 'USER_ENTERED' (parses formulas)
            """
            body = {'values': values}
            result = self.sheets.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption=input_option,
                body=body
            ).execute()
            return result
        
        def write_formula(self, cell: str, formula: str) -> Dict[str, Any]:
            """Write a single formula to a cell"""
            return self.write_values(cell, [[formula]], 'USER_ENTERED')
        
        def batch_update(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Execute multiple operations in a single API call"""
            body = {'requests': requests}
            result = self.sheets.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            return result
        
        # === CONDITIONAL FORMATTING ===
        
        def add_conditional_format_rule(self, sheet_id: int, 
                                       start_row: int, end_row: int,
                                       start_col: int, end_col: int,
                                       condition_type: str,
                                       condition_values: List[str],
                                       format_color: Dict[str, float]) -> Dict[str, Any]:
            """
            Add conditional formatting rule to a range
            
            Args:
                sheet_id: The ID of the sheet (0 for first sheet)
                start_row, end_row: Row indices (0-based)
                start_col, end_col: Column indices (0-based)
                condition_type: 'NUMBER_GREATER', 'NUMBER_LESS', 'TEXT_CONTAINS', etc.
                condition_values: Values for the condition
                format_color: RGB color dict {'red': 1.0, 'green': 0, 'blue': 0}
            """
            request = {
                'addConditionalFormatRule': {
                    'rule': {
                        'ranges': [{
                            'sheetId': sheet_id,
                            'startRowIndex': start_row,
                            'endRowIndex': end_row,
                            'startColumnIndex': start_col,
                            'endColumnIndex': end_col
                        }],
                        'booleanRule': {
                            'condition': {
                                'type': condition_type,
                                'values': [{'userEnteredValue': v} for v in condition_values]
                            },
                            'format': {
                                'backgroundColor': format_color
                            }
                        }
                    }
                }
            }
            return self.batch_update([request])
        
        def clear_conditional_formats(self, sheet_id: int) -> Dict[str, Any]:
            """Clear all conditional formatting from a sheet"""
            # First, get all existing rules
            spreadsheet = self.sheets.get(
                spreadsheetId=self.spreadsheet_id,
                fields='sheets.conditionalFormats'
            ).execute()
            
            # Create delete requests for each rule
            requests = []
            for sheet in spreadsheet.get('sheets', []):
                if sheet.get('properties', {}).get('sheetId') == sheet_id:
                    formats = sheet.get('conditionalFormats', [])
                    for i, _ in enumerate(formats):
                        requests.append({
                            'deleteConditionalFormatRule': {
                                'sheetId': sheet_id,
                                'index': 0  # Always delete index 0 as they shift
                            }
                        })
            
            return self.batch_update(requests) if requests else {}
        
        # === NAMED RANGES ===
        
        def create_named_range(self, name: str, sheet_id: int,
                             start_row: int, end_row: int,
                             start_col: int, end_col: int) -> Dict[str, Any]:
            """Create a named range"""
            request = {
                'addNamedRange': {
                    'namedRange': {
                        'name': name,
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': start_row,
                            'endRowIndex': end_row,
                            'startColumnIndex': start_col,
                            'endColumnIndex': end_col
                        }
                    }
                }
            }
            return self.batch_update([request])
        
        def get_named_ranges(self) -> List[Dict[str, Any]]:
            """Get all named ranges in the spreadsheet"""
            spreadsheet = self.sheets.get(
                spreadsheetId=self.spreadsheet_id,
                fields='namedRanges'
            ).execute()
            return spreadsheet.get('namedRanges', [])
        
        def delete_named_range(self, named_range_id: str) -> Dict[str, Any]:
            """Delete a named range by its ID"""
            request = {
                'deleteNamedRange': {
                    'namedRangeId': named_range_id
                }
            }
            return self.batch_update([request])
        
        # === FORMATTING ===
        
        def format_cells(self, sheet_id: int,
                        start_row: int, end_row: int,
                        start_col: int, end_col: int,
                        format_dict: Dict[str, Any]) -> Dict[str, Any]:
            """
            Apply formatting to a range of cells
            
            Format dict example:
            {
                'backgroundColor': {'red': 1.0, 'green': 1.0, 'blue': 0},
                'textFormat': {
                    'bold': True,
                    'fontSize': 12,
                    'foregroundColor': {'red': 0, 'green': 0, 'blue': 1}
                },
                'horizontalAlignment': 'CENTER',
                'numberFormat': {
                    'type': 'CURRENCY',
                    'pattern': '$#,##0.00'
                }
            }
            """
            request = {
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': start_row,
                        'endRowIndex': end_row,
                        'startColumnIndex': start_col,
                        'endColumnIndex': end_col
                    },
                    'cell': {
                        'userEnteredFormat': format_dict
                    },
                    'fields': 'userEnteredFormat'
                }
            }
            return self.batch_update([request])
        
        # === UTILITY FUNCTIONS ===
        
        def find_and_replace(self, find: str, replacement: str,
                           search_by_regex: bool = False,
                           match_case: bool = False,
                           match_entire_cell: bool = False,
                           all_sheets: bool = True) -> Dict[str, Any]:
            """Find and replace text across the spreadsheet"""
            request = {
                'findReplace': {
                    'find': find,
                    'replacement': replacement,
                    'searchByRegex': search_by_regex,
                    'matchCase': match_case,
                    'matchEntireCell': match_entire_cell,
                    'allSheets': all_sheets
                }
            }
            return self.batch_update([request])
        
        def get_sheet_properties(self) -> List[Dict[str, Any]]:
            """Get properties of all sheets in the spreadsheet"""
            spreadsheet = self.sheets.get(
                spreadsheetId=self.spreadsheet_id,
                fields='sheets.properties'
            ).execute()
            return [s['properties'] for s in spreadsheet.get('sheets', [])]
        
        def add_sheet(self, title: str) -> Dict[str, Any]:
            """Add a new sheet to the spreadsheet"""
            request = {
                'addSheet': {
                    'properties': {
                        'title': title
                    }
                }
            }
            return self.batch_update([request])
        
        def delete_sheet(self, sheet_id: int) -> Dict[str, Any]:
            """Delete a sheet by its ID"""
            request = {
                'deleteSheet': {
                    'sheetId': sheet_id
                }
            }
            return self.batch_update([request])
        
        def clear_range(self, range_name: str) -> Dict[str, Any]:
            """Clear values from a range"""
            result = self.sheets.values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            return result
        
        def a1_to_indices(self, a1_notation: str) -> tuple:
            """Convert A1 notation to row/column indices"""
            import re
            match = re.match(r'([A-Z]+)(\d+)', a1_notation.upper())
            if not match:
                raise ValueError(f"Invalid A1 notation: {a1_notation}")
            
            col_str, row_str = match.groups()
            
            # Convert column letters to index
            col_index = 0
            for char in col_str:
                col_index = col_index * 26 + (ord(char) - ord('A') + 1)
            col_index -= 1  # Zero-based
            
            # Convert row number to index
            row_index = int(row_str) - 1  # Zero-based
            
            return row_index, col_index

### Phase 4: Usage Examples

#### Example 4.1: Basic Reading and Writing

    # Initialize API
    sheets = GoogleSheetsAPI('credentials.json', 'your-spreadsheet-id')
    
    # Read values
    values = sheets.read_values('Sheet1!A1:C10')
    print(f"Values: {values}")
    
    # Read formulas
    formulas = sheets.read_formulas('Sheet1!A1:C10')
    print(f"Formulas: {formulas}")
    
    # Write values
    sheets.write_values('Sheet1!D1:D3', [['Value1'], ['Value2'], ['Value3']])
    
    # Write formula
    sheets.write_formula('Sheet1!E1', '=SUM(A1:D1)')

#### Example 4.2: Conditional Formatting

    # Highlight cells greater than 100
    sheets.add_conditional_format_rule(
        sheet_id=0,  # First sheet
        start_row=0, end_row=10,
        start_col=0, end_col=5,
        condition_type='NUMBER_GREATER',
        condition_values=['100'],
        format_color={'red': 1.0, 'green': 0.9, 'blue': 0.9}
    )
    
    # Highlight cells containing specific text
    sheets.add_conditional_format_rule(
        sheet_id=0,
        start_row=0, end_row=20,
        start_col=2, end_col=3,  # Column C
        condition_type='TEXT_CONTAINS',
        condition_values=['Important'],
        format_color={'red': 0.9, 'green': 1.0, 'blue': 0.9}
    )

#### Example 4.3: Named Ranges

    # Create named range for budget data
    sheets.create_named_range(
        name='BudgetData',
        sheet_id=0,
        start_row=1, end_row=100,  # Rows 2-100
        start_col=1, end_col=5      # Columns B-E
    )
    
    # Get all named ranges
    named_ranges = sheets.get_named_ranges()
    for nr in named_ranges:
        print(f"Named range: {nr['name']}")
    
    # Use named range in formula
    sheets.write_formula('Sheet1!F1', '=SUM(BudgetData)')

#### Example 4.4: Batch Operations

    # Multiple operations in one API call
    requests = [
        # Format header row
        {
            'repeatCell': {
                'range': {
                    'sheetId': 0,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': 10
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2},
                        'textFormat': {
                            'bold': True,
                            'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
                        }
                    }
                },
                'fields': 'userEnteredFormat'
            }
        },
        # Add formula
        {
            'updateCells': {
                'range': {
                    'sheetId': 0,
                    'startRowIndex': 10,
                    'endRowIndex': 11,
                    'startColumnIndex': 0,
                    'endColumnIndex': 1
                },
                'rows': [{
                    'values': [{
                        'userEnteredValue': {'formulaValue': '=SUM(A1:A9)'}
                    }]
                }],
                'fields': 'userEnteredValue'
            }
        }
    ]
    
    sheets.batch_update(requests)

### Phase 5: Claude Code Integration

#### Step 5.1: Teaching Claude Code

Create a file `CLAUDE_INSTRUCTIONS.md` in your project:

    # Google Sheets API Instructions
    
    You have access to a Google Sheets API interface through the GoogleSheetsAPI class.
    The spreadsheet ID is: [YOUR_SPREADSHEET_ID]
    
    ## Available Commands:
    
    ### Reading Data
    - "Read values from A1:C10"
    - "Get formulas from column D"
    - "Show me what's in the named range 'Budget'"
    
    ### Writing Data
    - "Set cell A1 to 100"
    - "Write formula =SUM(B:B) in cell A1"
    - "Fill A2:A10 with values 1 through 9"
    
    ### Formatting
    - "Highlight cells > 100 in red"
    - "Format A1:C1 as bold with yellow background"
    - "Add currency formatting to column D"
    
    ### Named Ranges
    - "Create named range 'Sales' for B2:B100"
    - "List all named ranges"
    
    ### Find and Replace
    - "Replace all 'Q1' with 'Q2'"
    - "Find all cells containing 'TODO'"
    
    ## Example Usage:
    
    from sheets_api import GoogleSheetsAPI
    sheets = GoogleSheetsAPI('credentials.json', '[SPREADSHEET_ID]')
    # Then use any of the methods described above

#### Step 5.2: Common Claude Code Commands

    # Initial setup
    "Set up Google Sheets API access using credentials.json"
    
    # Reading operations
    "Read all formulas from Sheet1 and identify which ones reference external sheets"
    "Get values from A1:Z100 and show me summary statistics"
    
    # Writing operations
    "Add a SUM formula at the bottom of each column with data"
    "Write today's date in cell A1 using a formula"
    
    # Complex operations
    "Find all cells with formulas containing VLOOKUP and replace with INDEX/MATCH"
    "Apply conditional formatting: green for positive, red for negative values"
    "Create named ranges for each column that has a header in row 1"
    
    # Analysis
    "Read all formulas and identify circular references"
    "Find all hardcoded values that should be formulas"

### Phase 6: Error Handling and Best Practices

#### Error Handling Patterns

    import time
    from googleapiclient.errors import HttpError
    
    def retry_operation(func, max_retries=3, delay=1):
        """Retry an operation with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return func()
            except HttpError as e:
                if e.resp.status in [429, 500, 503]:  # Rate limit or server error
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))
                        continue
                raise
        return None
    
    # Usage
    result = retry_operation(
        lambda: sheets.read_values('Sheet1!A1:C10')
    )

#### Best Practices

1. **Batch Operations**: Always use batch_update for multiple operations
2. **Range Notation**: Use sheet name in range (e.g., 'Sheet1!A1:C10')
3. **Formula Input**: Always use USER_ENTERED for formulas
4. **Rate Limiting**: Implement exponential backoff for retries
5. **Error Handling**: Catch and handle HttpError exceptions
6. **Caching**: Cache sheet IDs and named range IDs to reduce API calls
7. **Validation**: Validate ranges before making API calls
8. **Logging**: Log all API operations for debugging

### Phase 7: Testing and Validation

#### Test Script (test_api.py)

    import unittest
    from sheets_api import GoogleSheetsAPI
    
    class TestGoogleSheetsAPI(unittest.TestCase):
        def setUp(self):
            self.sheets = GoogleSheetsAPI('credentials.json', 'test-spreadsheet-id')
        
        def test_read_values(self):
            values = self.sheets.read_values('Sheet1!A1:A1')
            self.assertIsNotNone(values)
        
        def test_write_formula(self):
            result = self.sheets.write_formula('Sheet1!Z1', '=1+1')
            self.assertIn('updatedCells', result)
        
        def test_named_range(self):
            result = self.sheets.create_named_range(
                'TestRange', 0, 0, 10, 0, 5
            )
            self.assertIsNotNone(result)
    
    if __name__ == '__main__':
        unittest.main()

## Summary

This implementation provides Claude Code with all essential Google Sheets operations:

1. **Value and Formula Management**: Complete read/write capabilities
2. **Conditional Formatting**: Visual feedback and data highlighting  
3. **Named Ranges**: Clean formula references and better organization
4. **Batch Operations**: Efficient multi-operation execution
5. **Find and Replace**: Bulk text and formula updates
6. **Basic Formatting**: Colors, fonts, number formats

The simple API class (~300 lines) covers 95% of typical spreadsheet automation needs while remaining maintainable and easy for Claude Code to understand and use.

## Quick Start Checklist

- [ ] Create Google Cloud Project
- [ ] Enable Google Sheets API
- [ ] Create Service Account
- [ ] Download credentials.json
- [ ] Share spreadsheet with service account
- [ ] Install Python dependencies
- [ ] Copy sheets_api.py to project
- [ ] Test with simple read operation
- [ ] Create CLAUDE_INSTRUCTIONS.md
- [ ] Begin automation with Claude Code

## API Quotas and Limits

- **Read requests**: 100 per second
- **Write requests**: 100 per second  
- **Batch update**: 500 requests per batch
- **Cell limit**: 5 million cells per spreadsheet
- **API calls per day**: Unlimited for service accounts

## Troubleshooting

### Common Issues and Solutions

1. **Permission Denied**: Ensure spreadsheet is shared with service account email
2. **Invalid Range**: Check sheet name exists and range is valid
3. **Rate Limiting**: Implement exponential backoff retry logic
4. **Formula Errors**: Use USER_ENTERED input option for formulas
5. **Authentication Failed**: Verify credentials.json path and contents

## Next Steps

1. Implement the core API class
2. Test with your specific spreadsheet
3. Create custom functions for your use cases
4. Build automation workflows with Claude Code
5. Add monitoring and logging as needed