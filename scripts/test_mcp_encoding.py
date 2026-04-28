"""Quick smoke test: pipe a UTF-8 JSON-RPC request to the MCP server."""
import json
import subprocess
import os
import sys

request = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "query_knowledge_hub",
            "arguments": {"query": "李子昊参加了什么比赛", "top_k": 5},
        },
    },
    ensure_ascii=False,
) + "\n"

env = os.environ.copy()
env["PYTHONPATH"] = "D:/MODULAR-RAG-MCP-SERVER/src"

proc = subprocess.Popen(
    ["D:/MODULAR-RAG-MCP-SERVER/.venv/Scripts/python.exe", "-m", "mcp_server.server"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd="D:/MODULAR-RAG-MCP-SERVER",
    env=env,
)
stdout, stderr = proc.communicate(input=request.encode("utf-8"), timeout=60)
print("STDOUT:", stdout.decode("utf-8", errors="replace")[:500])
if stderr:
    err = stderr.decode("utf-8", errors="replace")
    for line in err.split("\n"):
        if any(k in line for k in ["ERROR", "Error", "Traceback", "Exception"]):
            print("STDERR:", line[:200])
