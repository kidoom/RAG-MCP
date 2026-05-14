
"""MCP server entrypoint using stdio transport.

E1 scope:
- Keep stdout strictly for JSON-RPC messages.
- Route operational logs to stderr.
- Support initialize handshake to prove transport availability.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Platform-agnostic UTF-8 stdio: on Windows sys.stdin/stdout default to the
# system locale encoding (e.g. cp936/gbk), which corrupts CJK query text sent
# by MCP clients over JSON-RPC.  Wrap the binary buffer so every client —
# Claude Code, VS Code, Continue, etc. — works without env-var gymnastics.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = __import__("io").TextIOWrapper(
        sys.stdin.buffer, encoding="utf-8", errors="replace"
    )
if hasattr(sys.stdout, "buffer"):
    sys.stdout = __import__("io").TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

from mcp_server.tools import get_tool_specs
from observability.logger import get_logger
from mcp_server.protocol_handler import JsonRpcError, ProtocolHandler


def _build_error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response object."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def run_stdio_server() -> None:
    """Run MCP server loop over stdio."""
    logger = get_logger("mcp_server")
    protocol_handler = ProtocolHandler(tools=get_tool_specs())
    logger.info("Starting MCP server on stdio")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.exception("Failed to decode JSON-RPC request")
            response = _build_error_response(None, -32700, "Parse error")
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()
            continue

        try:
            response = protocol_handler.dispatch(payload)
        except JsonRpcError as err:
            response = _build_error_response(payload.get("id"), err.code, err.message)
        except Exception:
            logger.exception("Unhandled server exception")
            response = _build_error_response(payload.get("id"), -32603, "Internal error")
        if response is None:
            continue

        sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        sys.stdout.flush()

    logger.info("MCP server stdin closed, shutting down")


def main() -> None:
    """Module entry point."""
    run_stdio_server()


if __name__ == "__main__":
    main()
