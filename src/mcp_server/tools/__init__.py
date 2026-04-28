"""MCP tools exposed by this server."""

from mcp_server.protocol_handler import ToolSpec

from .get_document_summary import get_document_summary
from .list_collections import list_collections
from .query_knowledge_hub import query_knowledge_hub


def get_tool_specs() -> list[ToolSpec]:
    """Return the list of currently registered MCP tool specs."""
    return [
        ToolSpec(
            name="query_knowledge_hub",
            description="Search the knowledge hub and return cited answers.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User query text"},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Number of results",
                    },
                    "collection": {
                        "type": "string",
                        "description": "Optional collection filter",
                    },
                },
                "required": ["query"],
            },
            handler=query_knowledge_hub,
        ),
        ToolSpec(
            name="list_collections",
            description="List available document collections.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=list_collections,
        ),
        ToolSpec(
            name="get_document_summary",
            description="Get title, summary and tags for one document.",
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document or chunk identifier"},
                    "collection": {"type": "string", "description": "Optional collection override"},
                },
                "required": ["doc_id"],
            },
            handler=get_document_summary,
        ),
    ]
