#!/usr/bin/env python3
"""
Modular RAG MCP Server - Main Entry Point

A modular, extensible RAG (Retrieval-Augmented Generation) server
with MCP (Model Context Protocol) support for intelligent Q&A systems.
"""

import sys
from pathlib import Path

# Add src to Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    """Main entry point for the Modular RAG MCP Server."""
    print("🤖 Modular RAG MCP Server")
    print("Version: 0.1.0")
    print("A modular RAG system with MCP support")
    print("\nUse 'python run_dashboard.py' to start the dashboard")
    print("Use 'python -m mcp_server' to start the MCP server")

if __name__ == "__main__":
    main()