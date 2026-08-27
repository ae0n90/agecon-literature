#!/usr/bin/env python3
"""Validate the repository's Skill entrypoint and UI metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

SKILL_DIR = Path("skills/agecon-literature-research")


def _frontmatter(text: str) -> dict[str, Any]:
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if match is None:
        raise SystemExit("SKILL.md has no valid YAML frontmatter")
    payload = yaml.safe_load(match.group(1))
    if not isinstance(payload, dict):
        raise SystemExit("SKILL.md frontmatter must be a mapping")
    return payload


def main() -> int:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    skill = _frontmatter(skill_text)
    if set(skill) != {"name", "description"}:
        raise SystemExit("Skill frontmatter must contain only name and description")
    if skill["name"] != SKILL_DIR.name:
        raise SystemExit("Skill name must match its directory")
    description = skill["description"]
    if not isinstance(description, str) or not (20 <= len(description) <= 1024):
        raise SystemExit("Skill description has an invalid length")

    ui_path = SKILL_DIR / "agents" / "openai.yaml"
    ui = yaml.safe_load(ui_path.read_text(encoding="utf-8"))
    interface = ui.get("interface", {})
    short = interface.get("short_description", "")
    if not 25 <= len(short) <= 64:
        raise SystemExit("short_description must contain 25-64 characters")
    prompt = interface.get("default_prompt", "")
    if f"${skill['name']}" not in prompt:
        raise SystemExit("default_prompt must explicitly mention the Skill name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
