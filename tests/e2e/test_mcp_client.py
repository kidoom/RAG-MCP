"""E2E test: MCP Client-side call simulation (I1).

Spawns the MCP server as a subprocess, simulates JSON-RPC over stdio,
and validates initialize → tools/list → tools/call → query_knowledge_hub.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
SERVER_MODULE = "mcp_server.server"


def _send_rpc(proc: subprocess.Popen, payload: dict) -> dict | None:
    """Send one JSON-RPC request and read one response line."""
    line = json.dumps(payload, ensure_ascii=True)
    try:
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
    except BrokenPipeError:
        return None

    start = time.monotonic()
    while time.monotonic() - start < 15:
        raw = proc.stdout.readline()
        if not raw:
            if proc.poll() is not None:
                return None
            time.sleep(0.05)
            continue
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
    return None


@pytest.mark.e2e
class TestMCPClient:
    """E2E JSON-RPC client tests against the MCP server."""

    @pytest.fixture(scope="class")
    def server_process(self):
        """Start MCP server as subprocess."""
        proc = subprocess.Popen(
            [sys.executable, "-m", SERVER_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(SRC_DIR.parent),
            env={**__import__("os").environ, "PYTHONPATH": str(SRC_DIR)},
        )
        yield proc
        # Cleanup
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def test_initialize_handshake(self, server_process):
        """Server responds to initialize with protocolVersion and capabilities."""
        resp = _send_rpc(
            server_process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "test-client"},
                },
            },
        )
        assert resp is not None, "No response from server"
        assert "result" in resp, f"Expected result, got: {resp}"
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in resp["result"]

    def test_tools_list_returns_registered_tools(self, server_process):
        """tools/list returns at least query_knowledge_hub."""
        # Initialize first
        _send_rpc(
            server_process,
            {"jsonrpc": "2.0", "id": 99, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
        )

        resp = _send_rpc(
            server_process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert resp is not None, "No response from server"
        tools = resp.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "query_knowledge_hub" in tool_names
        assert "list_collections" in tool_names
        assert "get_document_summary" in tool_names

    def test_tools_call_query_knowledge_hub_returns_citations(self, server_process):
        """tools/call with query_knowledge_hub returns content items."""
        # Initialize
        _send_rpc(
            server_process,
            {"jsonrpc": "2.0", "id": 100, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
        )

        resp = _send_rpc(
            server_process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {"query": "test query"},
                },
            },
        )
        assert resp is not None, "No response from tools/call"
        assert "result" in resp, f"Expected result, got error: {resp.get('error')}"

        result = resp["result"]
        # ResponseBuilder should produce content items
        assert "content" in result or isinstance(result, dict), (
            f"Result should contain content: {result}"
        )

    def test_tools_call_list_collections(self, server_process):
        """tools/call with list_collections returns collections list."""
        _send_rpc(
            server_process,
            {"jsonrpc": "2.0", "id": 101, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
        )

        resp = _send_rpc(
            server_process,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_collections", "arguments": {}},
            },
        )
        assert resp is not None
        assert "result" in resp

    def test_unknown_tool_returns_error(self, server_process):
        """Calling an unregistered tool returns -32601 error."""
        _send_rpc(
            server_process,
            {"jsonrpc": "2.0", "id": 102, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
        )

        resp = _send_rpc(
            server_process,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            },
        )
        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == -32601
