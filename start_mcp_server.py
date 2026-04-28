#!/usr/bin/env python3
"""Quick start script for Modular RAG MCP Server."""

import subprocess
import sys
from pathlib import Path

def main():
    """Start the MCP server."""
    project_root = Path(__file__).parent
    
    # Ensure venv is available
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    
    if not venv_python.exists():
        print("❌ Virtual environment not found. Please run setup first.")
        print("📝 Run: python .github/skills/setup/SKILL.md")
        sys.exit(1)
    
    print("🚀 Starting Modular RAG MCP Server...")
    print("📡 MCP Server ID: modular-rag")
    print("💡 Tip: Use @mcp in Copilot Chat to access available tools")
    print()
    
    # Run the MCP server
    cmd = [str(venv_python), "-m", "mcp_server"]
    subprocess.run(cmd, cwd=str(project_root))

if __name__ == "__main__":
    main()
