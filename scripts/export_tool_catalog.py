#!/usr/bin/env python3
"""Export or verify the checked-in MCP tool catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agecon_literature_mcp.tool_catalog import TOOL_CATALOG, export_tool_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("contracts/tools.json"),
    )
    args = parser.parse_args()
    expected = json.dumps({"schema_version": 1, "tools": TOOL_CATALOG}, indent=2) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            raise SystemExit("contracts/tools.json is stale; run scripts/export_tool_catalog.py")
        return 0
    export_tool_catalog(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
