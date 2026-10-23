"""FastMCP server registration for the literature workflow."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal, ParamSpec, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import Settings, load_settings
from .service import LiteratureService

_P = ParamSpec("_P")
_T = TypeVar("_T")

_STRICT_READS = {
    "lit_find_authors",
    "lit_session_summary",
    "zotero_match",
    "zotero_verify_import",
}
_OPEN_WORLD = {
    "lit_search",
    "lit_get_records",
    "lit_expand_relations",
    "pdf_download",
}


async def _run_blocking(
    function: Callable[_P, _T],
    /,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    """Keep browser, SQLite, keyring, and local HTTP work off the MCP event loop."""
    return await asyncio.to_thread(function, *args, **kwargs)


def _tool_annotations(name: str) -> ToolAnnotations:
    """Give clients conservative safety hints; local cache writes count as writes."""
    read_only = name in _STRICT_READS
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=False,
        idempotentHint=read_only,
        openWorldHint=name in _OPEN_WORLD,
    )


def create_server(
    settings: Settings | None = None,
    *,
    service: LiteratureService | None = None,
    host: str = "127.0.0.1",
    port: int = 7790,
) -> FastMCP[Any]:
    """Create a loopback-ready MCP server with explicit write-plan tools."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("AgEcon Literature MCP must bind to loopback")
    resolved_settings = settings or load_settings()
    literature = service or LiteratureService(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await _run_blocking(literature.close)

    server = FastMCP(
        name="agecon-literature-mcp",
        instructions=(
            "Search and inspect CNKI literature, validate PDF-only downloads, and "
            "use Zotero 10's official Local API. Download and Zotero mutation tools "
            "must only be called after the user reviews the matching plan and "
            "explicitly authorizes consumption of its confirmation token. Never "
            "represent candidate relations or abstract-only synthesis as complete."
        ),
        host=host,
        port=port,
        lifespan=lifespan,
    )

    @server.tool(name="lit_search", annotations=_tool_annotations("lit_search"))
    async def lit_search(
        query: str,
        field: Literal[
            "topic",
            "title",
            "author",
            "institution",
            "keyword",
            "abstract",
            "journal",
            "doi",
            "onebox",
        ] = "topic",
        year_from: int | None = None,
        year_to: int | None = None,
        journal: str | None = None,
        source_types: list[str] | None = None,
        sort_by: Literal["relevance", "date", "citation", "comprehensive"] = "relevance",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search CNKI with a supported structured field or broad onebox mode."""
        return await _run_blocking(
            literature.lit_search,
            query,
            field=field,
            year_from=year_from,
            year_to=year_to,
            journal=journal,
            source_types=source_types,
            sort_by=sort_by,
            limit=limit,
        )

    @server.tool(name="lit_get_records", annotations=_tool_annotations("lit_get_records"))
    async def lit_get_records(
        session_id: str | None = None,
        record_ids: list[str] | None = None,
        hydrate: bool = False,
        include_raw: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Read records; hydrate only selected records to retrieve detail metadata/abstracts."""
        return await _run_blocking(
            literature.lit_get_records,
            session_id=session_id,
            record_ids=record_ids,
            hydrate=hydrate,
            include_raw=include_raw,
            limit=limit,
        )

    @server.tool(name="lit_find_authors", annotations=_tool_annotations("lit_find_authors"))
    async def lit_find_authors(session_id: str, top_n: int = 20) -> dict[str, Any]:
        """Rank author frequency within one session, not field-wide influence."""
        return await _run_blocking(literature.lit_find_authors, session_id, top_n=top_n)

    @server.tool(
        name="lit_session_summary",
        annotations=_tool_annotations("lit_session_summary"),
    )
    async def lit_session_summary(session_id: str) -> dict[str, Any]:
        """Describe bounded session coverage without model-authored conclusions."""
        return await _run_blocking(literature.lit_session_summary, session_id)

    @server.tool(
        name="lit_expand_relations",
        annotations=_tool_annotations("lit_expand_relations"),
    )
    async def lit_expand_relations(
        record_id: str,
        direction: Literal["citations", "references", "similar"] = "citations",
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Expand only bounded relation candidates and report completeness."""
        return await _run_blocking(
            literature.lit_expand_relations,
            record_id,
            direction=direction,
            depth=depth,
            limit=limit,
        )

    @server.tool(name="zotero_match", annotations=_tool_annotations("zotero_match"))
    async def zotero_match(record_ids: list[str]) -> dict[str, Any]:
        """Read Zotero and report duplicate candidates without merging or writing."""
        return await _run_blocking(literature.zotero_match, record_ids)

    @server.tool(name="pdf_plan", annotations=_tool_annotations("pdf_plan"))
    async def pdf_plan(record_id: str) -> dict[str, Any]:
        """Create a local PDF download plan; this does not download bytes."""
        return await _run_blocking(literature.pdf_plan, record_id)

    @server.tool(name="pdf_download", annotations=_tool_annotations("pdf_download"))
    async def pdf_download(plan_id: str, confirmation_token: str) -> dict[str, Any]:
        """Download only after the user explicitly approves the exact plan."""
        return await _run_blocking(literature.pdf_download, plan_id, confirmation_token)

    @server.tool(
        name="zotero_plan_import",
        annotations=_tool_annotations("zotero_plan_import"),
    )
    async def zotero_plan_import(
        record_ids: list[str],
        mode: Literal[
            "standalone_pdf",
            "metadata_only",
            "metadata_with_pdf",
            "attach_pdf_to_existing",
        ] = "standalone_pdf",
        collection_key: str | None = None,
        pdf_paths: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Plan original-name standalone PDFs for Jasminum, without parent metadata."""
        return await _run_blocking(
            literature.zotero_plan_import,
            record_ids,
            mode=mode,
            collection_key=collection_key,
            pdf_paths=pdf_paths,
            tags=tags,
        )

    @server.tool(
        name="zotero_commit_import",
        annotations=_tool_annotations("zotero_commit_import"),
    )
    async def zotero_commit_import(
        plan_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        """Create Zotero objects only after explicit approval of the matching plan."""
        return await _run_blocking(
            literature.zotero_commit_import,
            plan_id,
            confirmation_token,
        )

    @server.tool(
        name="zotero_plan_resume",
        annotations=_tool_annotations("zotero_plan_resume"),
    )
    async def zotero_plan_resume(operation_id: str) -> dict[str, Any]:
        """Create a reviewable plan to resume one failed non-atomic import."""
        return await _run_blocking(literature.zotero_plan_resume, operation_id)

    @server.tool(
        name="zotero_resume_import",
        annotations=_tool_annotations("zotero_resume_import"),
    )
    async def zotero_resume_import(
        plan_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        """Continue a recoverable import only after approval of its resume plan."""
        return await _run_blocking(
            literature.zotero_resume_import,
            plan_id,
            confirmation_token,
        )

    @server.tool(
        name="zotero_verify_import",
        annotations=_tool_annotations("zotero_verify_import"),
    )
    async def zotero_verify_import(operation_id: str) -> dict[str, Any]:
        """Read back an import's parent metadata and attachment hash."""
        return await _run_blocking(literature.zotero_verify_import, operation_id)

    @server.tool(
        name="lit_export_session",
        annotations=_tool_annotations("lit_export_session"),
    )
    async def lit_export_session(
        session_id: str,
        format: Literal["json", "markdown"] = "json",
    ) -> dict[str, Any]:
        """Export local metadata plus an unfilled, evidence-aware synthesis scaffold."""
        return await _run_blocking(literature.lit_export_session, session_id, format=format)

    @server.resource(
        "agecon://doctor",
        name="agecon-literature-doctor",
        description="Read local setup status without writing to CNKI or Zotero.",
    )
    async def doctor() -> str:
        return json_dumps(await _run_blocking(literature.doctor))

    return server


def json_dumps(payload: Any) -> str:
    """Resource-safe JSON formatting kept separate from MCP's tool serializer."""
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["create_server"]
