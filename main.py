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

from core.settings import load_settings, SettingsError
from observability.logger import get_logger, set_log_level


def main():
    """Main entry point for the Modular RAG MCP Server."""
    try:
        # Load and validate configuration
        settings = load_settings()
        
        # Configure logger
        logger = get_logger()
        set_log_level(settings.observability.log_level)
        
        logger.info("🤖 Modular RAG MCP Server")
        logger.info("Version: 0.1.0")
        logger.info("Configuration loaded successfully")
        logger.info(f"  LLM Provider: {settings.llm.provider}")
        logger.info(f"  Embedding Provider: {settings.embedding.provider}")
        logger.info(f"  Vector Store: {settings.vector_store.provider}")
        
        print("🤖 Modular RAG MCP Server")
        print("Version: 0.1.0")
        print("A modular RAG system with MCP support")
        print("\nUse 'python run_dashboard.py' to start the dashboard")
        print("Use 'python -m mcp_server' to start the MCP server")
        
    except SettingsError as e:
        print(f"❌ Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()