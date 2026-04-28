"""Quick smoke test: test list_collections and query_knowledge_hub via MCP."""
import json
import subprocess
import os
import sys

env = os.environ.copy()
env["PYTHONPATH"] = "D:/MODULAR-RAG-MCP-SERVER/src"

PYTHON = "D:/MODULAR-RAG-MCP-SERVER/.venv/Scripts/python.exe"

# Test 1: list_collections
request = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_collections", "arguments": {}}},
    ensure_ascii=False,
) + "\n"

proc = subprocess.Popen(
    [PYTHON, "-m", "mcp_server.server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd="D:/MODULAR-RAG-MCP-SERVER", env=env,
)
stdout, stderr = proc.communicate(input=request.encode("utf-8"), timeout=60)
print("=== list_collections ===")
print(stdout.decode("utf-8", errors="replace")[:500])
if stderr:
    err = stderr.decode("utf-8", errors="replace")
    for line in err.split("\n"):
        if any(k in line for k in ["ERROR", "Error", "Traceback", "Exception"]):
            print("STDERR:", line[:200])
