"""Unit tests for MCP protocol handler."""

from __future__ import annotations

import pytest

from mcp_server.protocol_handler import JsonRpcError, ProtocolHandler, ToolSpec


@pytest.mark.unit
def test_handle_initialize_returns_server_info_and_capabilities():
    handler = ProtocolHandler()
    result = handler.handle_initialize({"protocolVersion": "2024-11-05"})

    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "modular-rag-mcp-server"
    assert "tools" in result["capabilities"]


@pytest.mark.unit
def test_dispatch_tools_list_returns_registered_tool_schemas():
    tool = ToolSpec(
        name="echo",
        description="Echo a message",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=lambda args: {"text": args.get("text", "")},
    )
    handler = ProtocolHandler([tool])

    response = handler.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert tools[0]["description"] == "Echo a message"
    assert tools[0]["inputSchema"]["type"] == "object"


@pytest.mark.unit
def test_dispatch_tools_call_routes_to_handler():
    tool = ToolSpec(
        name="echo",
        description="Echo a message",
        input_schema={"type": "object"},
        handler=lambda args: {"content": [{"type": "text", "text": args["text"]}]},
    )
    handler = ProtocolHandler([tool])

    response = handler.dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hello"}},
        }
    )

    assert response is not None
    assert response["result"]["content"][0]["text"] == "hello"


@pytest.mark.unit
def test_dispatch_unknown_method_returns_32601():
    handler = ProtocolHandler()

    with pytest.raises(JsonRpcError) as exc_info:
        handler.dispatch({"jsonrpc": "2.0", "id": 4, "method": "unknown/method"})

    assert getattr(exc_info.value, "code", None) == -32601


@pytest.mark.unit
def test_dispatch_invalid_params_returns_32602():
    handler = ProtocolHandler()

    with pytest.raises(JsonRpcError) as exc_info:
        handler.dispatch(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": "not-an-object"}
        )

    assert getattr(exc_info.value, "code", None) == -32602


@pytest.mark.unit
def test_dispatch_tool_internal_error_returns_32603():
    def broken_tool(_args):
        raise RuntimeError("unexpected failure detail")

    tool = ToolSpec(
        name="broken",
        description="Always fails",
        input_schema={"type": "object"},
        handler=broken_tool,
    )
    handler = ProtocolHandler([tool])

    with pytest.raises(JsonRpcError) as exc_info:
        handler.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "broken", "arguments": {}},
            }
        )

    assert getattr(exc_info.value, "code", None) == -32603
    assert "unexpected failure detail" not in str(exc_info.value)
