#!/usr/bin/env python3
"""Test script for MCP server.

This script tests the MCP server by sending JSON-RPC requests and verifying responses.
"""

import json
import subprocess
import sys
import time


def send_request(process, request):
    """Send a JSON-RPC request to the server and return the response."""
    request_json = json.dumps(request) + "\n"
    process.stdin.write(request_json)
    process.stdin.flush()

    # Read response
    response_line = process.stdout.readline()

    # Debug: print what we got
    if not response_line.strip():
        # Check stderr for errors
        stderr_output = process.stderr.read()
        if stderr_output:
            print(f"   Server stderr: {stderr_output}")
        raise Exception("Got empty response from server")

    return json.loads(response_line)


def test_mcp_server():
    """Test the MCP server with basic requests."""
    print("Starting MCP server test...")

    # Start the server
    server_path = "/home/john/src/sheet-cli/mcp-server/server.py"
    venv_python = "/home/john/src/sheet-cli/venv/bin/python"
    process = subprocess.Popen(
        [venv_python, server_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd="/home/john/src/sheet-cli"  # Run from project root for credentials
    )

    # Give server time to start
    time.sleep(0.5)

    try:
        # Test 1: Initialize
        print("\n1. Testing initialize...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        response = send_request(process, init_request)
        assert "result" in response, f"Initialize failed: {response}"
        assert response["result"]["protocolVersion"] == "2024-11-05"
        print("   ✓ Initialize successful")

        # Test 2: List tools
        print("\n2. Testing tools/list...")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        response = send_request(process, tools_request)
        assert "result" in response, "Tools list failed"
        tools = response["result"]["tools"]
        assert len(tools) == 4, f"Expected 4 tools, got {len(tools)}"

        tool_names = [t["name"] for t in tools]
        expected_tools = ["read_cells", "write_cells", "read_metadata", "write_metadata"]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"
        print(f"   ✓ Found all 4 tools: {', '.join(tool_names)}")

        # Test 3: Invalid method
        print("\n3. Testing invalid method...")
        invalid_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "invalid_method",
            "params": {}
        }
        response = send_request(process, invalid_request)
        assert "error" in response, "Expected error for invalid method"
        assert response["error"]["code"] == -32601
        print("   ✓ Invalid method handled correctly")

        print("\n✅ All tests passed!")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        # Print any stderr output
        stderr_data = process.stderr.read()
        if stderr_data:
            print(f"Server stderr:\n{stderr_data}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        # Print any stderr output
        try:
            stderr_data = process.stderr.read()
            if stderr_data:
                print(f"Server stderr:\n{stderr_data}")
        except:
            pass
        return False
    finally:
        # Clean up
        process.terminate()
        process.wait()

    return True


if __name__ == "__main__":
    success = test_mcp_server()
    sys.exit(0 if success else 1)
