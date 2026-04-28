"""JSON-RPC 2.0 protocol handler for MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "modular-rag-mcp-server"
SERVER_VERSION = "0.1.0"

ToolFunc = Callable[[dict[str, Any]], dict[str, Any]]


class JsonRpcError(Exception):
    """Structured JSON-RPC error that maps to protocol error responses."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolSpec:
    """Schema and implementation for one MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolFunc

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ProtocolHandler:
    """Handle MCP JSON-RPC methods and capability negotiation."""

    def __init__(self, tools: list[ToolSpec] | None = None):
        self._tools: dict[str, ToolSpec] = {}
        for spec in tools or []:
            self._tools[spec.name] = spec

    def handle_initialize(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Handle initialize request and return server capabilities."""
        if params is not None and not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params: initialize params must be an object")

        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"tools": {}},
        }

    def handle_tools_list(self) -> dict[str, Any]:
        """Return registered tools schema list."""
        return {"tools": [spec.to_dict() for spec in self._tools.values()]}

    def handle_tools_call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        """Route tools/call request to a registered tool."""
        if not isinstance(name, str) or not name:
            raise JsonRpcError(-32602, "Invalid params: tools/call requires non-empty 'name'")
        if arguments is not None and not isinstance(arguments, dict):
            raise JsonRpcError(-32602, "Invalid params: 'arguments' must be an object")

        spec = self._tools.get(name)
        if spec is None:
            raise JsonRpcError(-32601, f"Method not found: tool '{name}' is not registered")

        try:
            return spec.handler(arguments or {})
        except (ValueError, TypeError) as exc:
            raise JsonRpcError(-32602, f"Invalid params: {exc}")
        except JsonRpcError:
            raise
        except Exception:
            # Do not leak stack traces in protocol responses.
            raise JsonRpcError(-32603, "Internal error")

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch one JSON-RPC payload and build protocol-compliant response."""
        if not isinstance(payload, dict):
            raise JsonRpcError(-32600, "Invalid Request")

        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params")

        if method is None or not isinstance(method, str):
            raise JsonRpcError(-32600, "Invalid Request")

        # Notification: no response body by design.
        if request_id is None:
            return None

        if method == "initialize":
            result = self.handle_initialize(params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        if method == "tools/list":
            if params not in (None, {}):
                raise JsonRpcError(-32602, "Invalid params: tools/list does not accept params")
            result = self.handle_tools_list()
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        if method == "tools/call":
            if not isinstance(params, dict):
                raise JsonRpcError(-32602, "Invalid params: tools/call params must be an object")
            result = self.handle_tools_call(
                name=params.get("name", ""),
                arguments=params.get("arguments"),
            )
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        raise JsonRpcError(-32601, f"Method not found: {method}")
