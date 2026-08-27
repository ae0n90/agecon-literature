#!/usr/bin/env python3
"""Install the companion Skill into a personal Codex skill directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination-root",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "skills" / "agecon-literature-research"
    destination = args.destination_root.expanduser() / source.name
    if destination.exists() and not args.force:
        raise SystemExit(f"destination exists: {destination}; pass --force to replace it")
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
