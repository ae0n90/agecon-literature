"""Single source of truth for the public MCP tool contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "lit_search",
        "category": "cnki_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Search CNKI and persist a replayable local result session.",
    },
    {
        "name": "lit_get_records",
        "category": "cnki_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Read stored records and optionally retrieve selected abstracts.",
    },
    {
        "name": "lit_find_authors",
        "category": "local_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Aggregate authors within one bounded search session.",
    },
    {
        "name": "lit_session_summary",
        "category": "local_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Describe result coverage by year, source, keyword, and evidence level.",
    },
    {
        "name": "lit_expand_relations",
        "category": "cnki_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Run bounded candidate-citation expansion with completeness flags.",
    },
    {
        "name": "zotero_match",
        "category": "zotero_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Report exact and fuzzy candidates from the local Zotero library.",
    },
    {
        "name": "pdf_plan",
        "category": "local_plan",
        "read_only_external": True,
        "destructive": False,
        "description": "Create a short-lived plan for one local PDF-only download.",
    },
    {
        "name": "pdf_download",
        "category": "local_write",
        "read_only_external": False,
        "destructive": False,
        "description": "Check download access; preserve and verify the original PDF.",
    },
    {
        "name": "zotero_plan_import",
        "category": "local_plan",
        "read_only_external": True,
        "destructive": False,
        "description": "Plan original-name standalone PDF import; Jasminum owns parent metadata.",
    },
    {
        "name": "zotero_commit_import",
        "category": "zotero_write",
        "read_only_external": False,
        "destructive": False,
        "description": "Consume a confirmed plan and create Zotero items or attachments.",
    },
    {
        "name": "zotero_plan_resume",
        "category": "local_plan",
        "read_only_external": True,
        "destructive": False,
        "description": "Create a short-lived plan to continue one recoverable import.",
    },
    {
        "name": "zotero_resume_import",
        "category": "zotero_write",
        "read_only_external": False,
        "destructive": False,
        "description": "Consume a resume plan and continue from the persisted safe state.",
    },
    {
        "name": "zotero_verify_import",
        "category": "zotero_read",
        "read_only_external": True,
        "destructive": False,
        "description": "Read back Zotero metadata and attachment hashes for verification.",
    },
    {
        "name": "lit_export_session",
        "category": "local_write",
        "read_only_external": True,
        "destructive": False,
        "description": "Export source records and an empty synthesis scaffold locally.",
    },
]

TOOL_BY_NAME = {tool["name"]: tool for tool in TOOL_CATALOG}


def export_tool_catalog(destination: Path) -> None:
    """Write the stable catalog used by Skill/CI contract checks."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"schema_version": 1, "tools": TOOL_CATALOG}, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = ["TOOL_BY_NAME", "TOOL_CATALOG", "export_tool_catalog"]
