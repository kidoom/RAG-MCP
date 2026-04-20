#!/usr/bin/env python3
"""
Dashboard launcher for Modular RAG MCP Server
"""

import subprocess
import sys
import os

def main():
    # Activate virtual environment
    venv_path = ".venv/Scripts/activate.ps1" if os.name == 'nt' else ".venv/bin/activate"

    if os.name == 'nt':
        # Windows
        cmd = f'powershell -ExecutionPolicy Bypass -Command "& {venv_path}; streamlit run src/dashboard/app.py"'
    else:
        # Unix-like
        cmd = f'source {venv_path} && streamlit run src/dashboard/app.py'

    print("Starting dashboard...")
    print(f"Command: {cmd}")

    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to start dashboard: {e}")
        print("Make sure all dependencies are installed:")
        print("pip install -e \".[dev]\"")
        sys.exit(1)

if __name__ == "__main__":
    main()