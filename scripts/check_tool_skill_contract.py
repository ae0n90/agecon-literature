#!/usr/bin/env python3
"""Fail when MCP and companion Skill tool names drift apart."""

from __future__ import annotations

import re
from pathlib import Path

from agecon_literature_mcp.tool_catalog import TOOL_CATALOG


def main() -> int:
    skill = Path("skills/agecon-literature-research/SKILL.md").read_text(encoding="utf-8")
    match = re.search(
        r"<!-- tool-contract:start -->(.*?)<!-- tool-contract:end -->",
        skill,
        flags=re.DOTALL,
    )
    if match is None:
        raise SystemExit("Skill is missing its tool-contract block")
    skill_names = set(re.findall(r"`([a-z][a-z0-9_]*)`", match.group(1)))
    catalog_names = {tool["name"] for tool in TOOL_CATALOG}
    if skill_names != catalog_names:
        missing = sorted(catalog_names - skill_names)
        unknown = sorted(skill_names - catalog_names)
        raise SystemExit(f"tool contract drift: missing={missing}, unknown={unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
