"""Integration tests for MCP server stdio transport entrypoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from core.response import MultimodalAssembler, ResponseBuilder
from core.types import RetrievalResult
from ingestion.storage import ImageStorage


@pytest.mark.integration
def test_mcp_server_initialize_via_stdio(project_root):
    """Server should complete initialize over stdio with clean stdout."""
    env = dict(os.environ)
    src_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    )

    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=project_root,
        env=env,
    )

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {}},
    }

    assert process.stdin is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()

    assert process.stdout is not None
    raw_response = process.stdout.readline().strip()
    assert raw_response, "MCP server did not return initialize response"

    response = json.loads(raw_response)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "modular-rag-mcp-server"
    assert "tools" in response["result"]["capabilities"]

    # Clean shutdown by closing stdin and waiting process exits.
    process.stdin.close()
    process.wait(timeout=5)
    assert process.returncode == 0

    assert process.stderr is not None
    stderr_content = process.stderr.read()
    assert "Starting MCP server on stdio" in stderr_content


@pytest.mark.integration
def test_mcp_server_query_knowledge_hub_tool_call(project_root):
    """Server should expose query_knowledge_hub and return MCP content."""
    env = dict(os.environ)
    src_path = str(project_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    )

    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=project_root,
        env=env,
    )

    assert process.stdin is not None
    assert process.stdout is not None

    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {}},
            }
        )
        + "\n"
    )
    process.stdin.flush()
    _ = process.stdout.readline()

    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
    process.stdin.flush()
    tools_response = json.loads(process.stdout.readline().strip())
    names = [item["name"] for item in tools_response["result"]["tools"]]
    assert "query_knowledge_hub" in names
    assert "list_collections" in names
    assert "get_document_summary" in names

    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {"query": "如何配置 Azure", "top_k": 3},
                },
            }
        )
        + "\n"
    )
    process.stdin.flush()
    call_response = json.loads(process.stdout.readline().strip())

    assert call_response["id"] == 3
    assert "content" in call_response["result"]
    assert call_response["result"]["content"][0]["type"] == "text"
    assert "structuredContent" in call_response["result"]
    assert "citations" in call_response["result"]["structuredContent"]

    process.stdin.close()
    process.wait(timeout=5)
    assert process.returncode == 0


@pytest.mark.integration
def test_response_builder_includes_image_content(tmp_path):
    """E6: builder should append image blocks for chunk image references."""
    image_storage = ImageStorage(
        image_root=str(tmp_path / "images"),
        db_path=str(tmp_path / "image_index.db"),
    )
    image_storage.save_image(
        image_id="img-1",
        image_bytes=b"\x89PNG\r\n\x1a\nfake",
        collection="test",
        doc_hash="doc-1",
        extension=".png",
    )

    result = RetrievalResult(
        chunk_id="chunk-1",
        score=0.9,
        text="chunk with image",
        metadata={"image_refs": ["img-1"], "source_path": "docs/a.md"},
    )
    builder = ResponseBuilder(multimodal_assembler=MultimodalAssembler(image_storage=image_storage))
    out = builder.build([result], query="image query")

    image_items = [item for item in out["content"] if item.get("type") == "image"]
    assert len(image_items) == 1
    assert image_items[0]["mimeType"] == "image/png"
    assert isinstance(image_items[0]["data"], str) and image_items[0]["data"]
