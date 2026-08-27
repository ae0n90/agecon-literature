#!/usr/bin/env python3
"""Create a usable uv environment and verify the project import."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(*arguments: str) -> None:
    subprocess.run(arguments, check=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    run(
        "uv",
        "sync",
        "--extra",
        "dev",
        "--no-editable",
        "--reinstall-package",
        "agecon-literature-mcp",
    )
    environment = root / ".venv"
    # Recent macOS/Python combinations skip .pth files carrying UF_HIDDEN.
    # uv marks .venv hidden for Finder, so clear only that local filesystem flag.
    if sys.platform == "darwin" and environment.exists():
        run("chflags", "-R", "nohidden", str(environment))
    run(
        "uv",
        "run",
        "--no-sync",
        "python",
        "-c",
        "import agecon_literature_mcp; print(agecon_literature_mcp.__version__)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
