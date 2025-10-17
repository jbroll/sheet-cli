#!/bin/bash

# Shell script to start the Google Sheets MCP server with proper environment setup
# This script activates the virtual environment and runs the MCP server

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Change to project root (for venv activation)
cd "$PROJECT_ROOT"

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Run the MCP server
exec python3 "$SCRIPT_DIR/sheet-service.py"
