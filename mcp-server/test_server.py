#!/usr/bin/env python3
"""Smoke tests for the v2 MCP server.

Starts sheet-service.py as a subprocess, sends JSON-RPC requests over
stdio, and verifies the tool catalog + error paths. No Google API calls.
"""

import json
import os
import subprocess
import sys


SERVER_PATH = os.path.join(os.path.dirname(__file__), "sheet-service.py")
VENV_PYTHON = os.path.join(os.path.dirname(__file__), "..", "venv", "bin", "python")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

EXPECTED_TOOLS = [
    "sheets_get",
    "sheets_put",
    "sheets_del",
    "sheets_new",
    "sheets_copy",
    "sheets_move",
    "sheets_batch_update",
]


def send_request(process, request):
    assert process.stdin is not None and process.stdout is not None
    line = json.dumps(request) + "\n"
    process.stdin.write(line)
    process.stdin.flush()
    response = process.stdout.readline()
    if not response.strip():
        assert process.stderr is not None
        err = process.stderr.read()
        raise RuntimeError(f"empty response; stderr:\n{err}")
    return json.loads(response)


def test_mcp_server():
    print("Starting MCP server test...")

    process = subprocess.Popen(
        [VENV_PYTHON, SERVER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=PROJECT_ROOT,
    )

    try:
        # 1. initialize
        print("\n1. initialize...")
        response = send_request(process, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1.0.0"}},
        })
        assert "result" in response, f"initialize failed: {response}"
        assert response["result"]["protocolVersion"] == "2024-11-05"
        assert response["result"]["serverInfo"]["version"] == "2.0.0"
        print("   \u2713 ok")

        # 2. tools/list
        print("\n2. tools/list...")
        response = send_request(process, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        assert "result" in response, f"tools/list failed: {response}"
        tools = response["result"]["tools"]
        names = [t["name"] for t in tools]
        assert names == EXPECTED_TOOLS, (
            f"expected tools {EXPECTED_TOOLS}, got {names}"
        )
        for t in tools:
            assert "description" in t and t["description"]
            assert "inputSchema" in t
        print(f"   \u2713 {len(tools)} tools: {', '.join(names)}")

        # 3. unknown method
        print("\n3. unknown method...")
        response = send_request(process, {
            "jsonrpc": "2.0", "id": 3, "method": "does_not_exist", "params": {},
        })
        assert "error" in response
        assert response["error"]["code"] == -32601
        print("   \u2713 method not found")

        # 4. tools/call unknown tool → -32603
        print("\n4. tools/call unknown tool...")
        response = send_request(process, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        })
        assert "error" in response
        assert response["error"]["code"] == -32603
        print("   \u2713 internal error")

        # 5. grammar error → -32602
        print("\n5. grammar error...")
        response = send_request(process, {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "sheets_get", "arguments": {"target": "SID:Sheet!@@@"}},
        })
        assert "error" in response, f"expected error, got {response}"
        assert response["error"]["code"] == -32602
        print("   \u2713 grammar error routed")

        print("\n\u2705 All tests passed!")
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    try:
        test_mcp_server()
    except AssertionError as e:
        print(f"\n\u274c Test failed: {e}")
        sys.exit(1)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
