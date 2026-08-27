from __future__ import annotations

import asyncio
import re
from pathlib import Path
from threading import get_ident
from typing import Any

from agecon_literature_mcp.config import Settings
from agecon_literature_mcp.server import create_server
from agecon_literature_mcp.tool_catalog import TOOL_CATALOG


class ListingOnlyService:
    def close(self) -> None:
        return

    def doctor(self) -> dict[str, Any]:
        return {"ok": True}


class ThreadCheckingService(ListingOnlyService):
    def __init__(self) -> None:
        self.called_thread: int | None = None

    def lit_search(self, query: str, **_: Any) -> dict[str, Any]:
        self.called_thread = get_ident()
        return {"query": query}


def test_server_and_skill_exactly_match_catalog(tmp_path: Path) -> None:
    settings = Settings(runtime={"data_dir": tmp_path})
    server = create_server(
        settings,
        service=ListingOnlyService(),  # type: ignore[arg-type]
    )
    tools = asyncio.run(server.list_tools())
    server_names = {tool.name for tool in tools}
    catalog_names = {item["name"] for item in TOOL_CATALOG}
    assert server_names == catalog_names

    skill = Path("skills/agecon-literature-research/SKILL.md").read_text(encoding="utf-8")
    block = re.search(
        r"<!-- tool-contract:start -->(.*?)<!-- tool-contract:end -->",
        skill,
        flags=re.DOTALL,
    )
    assert block is not None
    skill_names = set(re.findall(r"`([a-z][a-z0-9_]*)`", block.group(1)))
    assert skill_names == catalog_names


def test_write_tools_are_non_destructive_but_not_read_only(tmp_path: Path) -> None:
    server = create_server(
        Settings(runtime={"data_dir": tmp_path}),
        service=ListingOnlyService(),  # type: ignore[arg-type]
    )
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in ("pdf_download", "zotero_commit_import", "zotero_resume_import"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is False


def test_blocking_service_calls_run_off_the_mcp_event_loop(tmp_path: Path) -> None:
    service = ThreadCheckingService()
    server = create_server(
        Settings(runtime={"data_dir": tmp_path}),
        service=service,  # type: ignore[arg-type]
    )

    async def invoke() -> int:
        event_loop_thread = get_ident()
        await server.call_tool("lit_search", {"query": "农业社会化服务"})
        return event_loop_thread

    event_loop_thread = asyncio.run(invoke())
    assert service.called_thread is not None
    assert service.called_thread != event_loop_thread
