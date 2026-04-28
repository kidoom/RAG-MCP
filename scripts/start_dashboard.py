#!/usr/bin/env python
"""Launch script for the Modular RAG MCP Server Dashboard.

Usage:
    python scripts/start_dashboard.py
    python scripts/start_dashboard.py --port 8501
"""

from __future__ import annotations

import os
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _venv_executable() -> str:
    """Return the venv Python path, falling back to sys.executable."""
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    # Try Unix-style venv
    unix_venv = REPO_ROOT / ".venv" / "bin" / "python"
    if unix_venv.is_file():
        return str(unix_venv)
    return sys.executable


def main() -> None:
    parser = ArgumentParser(description="Start the RAG Dashboard")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit server port")
    parser.add_argument("--host", type=str, default="localhost", help="Streamlit server host")
    parser.add_argument(
        "--extra-args",
        type=str,
        default="",
        help="Additional arguments to pass to streamlit run (space-separated)",
    )
    args = parser.parse_args()

    app_path = SRC_DIR / "observability" / "dashboard" / "app.py"
    if not app_path.is_file():
        print(f"Error: Dashboard app not found at {app_path}", file=sys.stderr)
        sys.exit(1)

    python_exe = _venv_executable()
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC_DIR}{os.pathsep}{existing}" if existing else str(SRC_DIR)

    cmd = [
        python_exe,
        "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(args.port),
        "--server.address", args.host,
        "--browser.serverAddress", args.host,
    ]
    if args.extra_args:
        cmd.extend(args.extra_args.split())

    print(f"Venv:   {python_exe}")
    print(f"App:    {app_path}")
    print(f"URL:    http://{args.host}:{args.port}")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, env=env)


if __name__ == "__main__":
    main()
