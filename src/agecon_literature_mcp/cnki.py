"""CNKI adapter around the pinned SepineTam browser implementation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from .config import CnkiSettings
from .exceptions import PdfValidationError, SetupRequired, SourceUnavailable
from .models import EvidenceLevel, LiteratureRecord, SearchSpec, stable_id
from .pdf import validate_pdf

_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")
_GENERIC_SOURCE_IDS = frozenset(
    {
        "abstract",
        "article",
        "default",
        "detail",
        "download",
        "index",
        "kcms2",
    }
)


def _year_from(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and (match := _YEAR_PATTERN.search(value)):
        return int(match.group())
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in re.split(r"[;\uff1b]", value) if item.strip()]
    return []


def _stable_source_id(payload: dict[str, Any]) -> str | None:
    """Prefer CNKI filename/database keys and discard volatile v-token URLs."""
    raw_filename = payload.get("filename")
    if raw_filename and str(raw_filename).strip().casefold() not in _GENERIC_SOURCE_IDS:
        filename = str(raw_filename).strip()
        database = str(payload.get("dbcode") or payload.get("dbname") or "CNKI").strip()
        return f"{database.upper()}:{filename}"

    candidates = (payload.get("article_id"), payload.get("url"))
    for candidate in candidates:
        if not candidate:
            continue
        value = str(candidate).strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return value if value.casefold() not in _GENERIC_SOURCE_IDS else None
        query = {key.casefold(): values for key, values in parse_qs(parsed.query).items()}
        filename_values = query.get("filename")
        query_filename = filename_values[0] if filename_values else None
        if query_filename:
            database_values = query.get("dbcode") or query.get("dbname")
            database = database_values[0] if database_values else "CNKI"
            return f"{database.upper()}:{query_filename}"
        path_match = re.search(r"/article/([^/?#]+)", parsed.path)
        if path_match and path_match.group(1).casefold() not in _GENERIC_SOURCE_IDS:
            return path_match.group(1)
    return None


def canonicalize_cnki(
    payload: dict[str, Any],
    *,
    existing_id: str | None = None,
) -> LiteratureRecord:
    """Map upstream search/detail shapes into one source-preserving record."""
    title = str(payload.get("title") or "").strip()
    if not title:
        raise SourceUnavailable("CNKI result did not contain a title")
    authors = _string_list(payload.get("authors"))
    year = _year_from(payload.get("year")) or _year_from(payload.get("date"))
    source_id = _stable_source_id(payload)
    raw_url = payload.get("url") or payload.get("article_id")
    url = str(raw_url) if raw_url and urlparse(str(raw_url)).scheme in {"http", "https"} else None
    abstract = payload.get("abstract")
    abstract_text = str(abstract).strip() if abstract else None
    evidence_level = (
        EvidenceLevel.ABSTRACT
        if abstract_text
        else (
            EvidenceLevel.METADATA
            if any(
                payload.get(key) for key in ("doi", "keywords", "institution", "volume", "issue")
            )
            else EvidenceLevel.SEARCH_RESULT
        )
    )
    institution_value = payload.get("institution") or payload.get("institutions")
    source_title = payload.get("source") or payload.get("journal")
    record_id = existing_id or stable_id("cnki", source_id, title, authors, year)
    return LiteratureRecord(
        id=record_id,
        source="cnki",
        source_id=source_id,
        title=title,
        authors=authors,
        institutions=_string_list(institution_value),
        abstract=abstract_text,
        keywords=_string_list(payload.get("keywords")),
        year=year,
        source_title=str(source_title).strip() if source_title else None,
        volume=str(payload["volume"]).strip() if payload.get("volume") else None,
        issue=str(payload["issue"]).strip() if payload.get("issue") else None,
        pages=str(payload["pages"]).strip() if payload.get("pages") else None,
        doi=str(payload["doi"]).strip() if payload.get("doi") else None,
        url=url,
        download_url=str(payload["download_url"]) if payload.get("download_url") else None,
        citation_count=(
            int(payload["citation_count"])
            if isinstance(payload.get("citation_count"), (int, str))
            and str(payload["citation_count"]).isdigit()
            else None
        ),
        evidence_level=evidence_level,
        raw=payload,
    )


class CnkiProvider:
    """Lazily owns one authenticated CNKI browser worker."""

    def __init__(self, settings: CnkiSettings) -> None:
        self.settings = settings
        self._service: Any | None = None
        self._lock = RLock()

    @staticmethod
    def _imports() -> tuple[Any, Any]:
        try:
            from cnki_mcp.core import auth  # type: ignore[import-untyped]
            from cnki_mcp.server.tool_registry import (  # type: ignore[import-untyped]
                McpToolService,
            )
        except ImportError as exc:  # pragma: no cover - packaging failure
            raise SetupRequired("the pinned cnki-mcp dependency is not installed") from exc
        return auth, McpToolService

    def status(self) -> dict[str, Any]:
        """Inspect profile availability without initiating a network request."""
        auth, _ = self._imports()
        profiles = auth.list_profiles()
        return {
            "configured_profile": self.settings.profile,
            "available_profiles": profiles,
            "ready": self.settings.profile in profiles,
            "browser_running": bool(self._service and self._service.worker.is_running),
            "profile_storage": "~/.cnki-mcp/profiles (managed by pinned cnki-mcp)",
        }

    def initialize_profile(self) -> dict[str, Any]:
        """Run the explicit interactive CNKI profile initialization flow."""
        auth, _ = self._imports()
        try:
            result = auth.login(profile=self.settings.profile, headless=False)
            auth.set_default_profile(self.settings.profile)
        except Exception as exc:
            raise SetupRequired(f"CNKI profile initialization failed: {exc}") from exc
        return {
            "success": bool(result.success),
            "profile": self.settings.profile,
            "message": result.message,
        }

    def _ensure_service(self) -> Any:
        with self._lock:
            if self._service is not None and self._service.worker.is_running:
                return self._service
            auth, service_type = self._imports()
            try:
                auth.require_profile(self.settings.profile)
            except Exception as exc:
                raise SetupRequired(
                    "CNKI browser profile is missing; run "
                    f"'agecon-literature cnki-init --profile {self.settings.profile}'"
                ) from exc
            service = self._service or service_type()
            try:
                service.login(self.settings.profile)
            except Exception as exc:
                raise SetupRequired(f"CNKI login/session check failed: {exc}") from exc
            self._service = service
            return service

    def close(self) -> None:
        with self._lock:
            if self._service is not None:
                self._service.close()

    def search(self, spec: SearchSpec) -> list[LiteratureRecord]:
        """Execute a bounded search and preserve the exact source payload."""
        limit = min(spec.limit, self.settings.max_results)
        service = self._ensure_service()
        try:
            if spec.field == "onebox":
                rows = service.easy_search(spec.query, limit=limit, sort_by=spec.sort_by)
            else:
                allowed_fields = {
                    "topic": "subject",
                    "title": "title",
                    "author": "author",
                    "institution": "institution",
                    "keyword": "keywords",
                    "abstract": "abstract",
                    "journal": "journal",
                    "doi": "doi",
                }
                argument = allowed_fields.get(spec.field)
                if argument is None:
                    raise ValueError(f"unsupported CNKI search field: {spec.field}")
                kwargs: dict[str, Any] = {
                    argument: spec.query,
                    "year_from": spec.year_from,
                    "year_to": spec.year_to,
                    "source_types": spec.source_types,
                    "sort_by": spec.sort_by,
                    "limit": limit,
                }
                if spec.journal and argument != "journal":
                    kwargs["journal"] = spec.journal
                rows = service.advanced_search(**kwargs)
        except (ValueError, SetupRequired):
            raise
        except Exception as exc:
            raise SourceUnavailable(f"CNKI search failed: {exc}") from exc
        return [canonicalize_cnki(row) for row in rows]

    def hydrate(self, record: LiteratureRecord) -> LiteratureRecord:
        """Retrieve detail-page metadata and abstract for a stored result URL."""
        target = record.url or record.source_id
        if not target:
            raise SourceUnavailable(f"record {record.id} has no CNKI detail URL")
        service = self._ensure_service()
        try:
            payload = service.get_info_from_url(target)
        except Exception as exc:
            raise SourceUnavailable(f"CNKI detail retrieval failed for {record.id}: {exc}") from exc
        return canonicalize_cnki(payload, existing_id=record.id)

    def candidate_citations(
        self,
        record: LiteratureRecord,
        *,
        limit: int,
    ) -> list[LiteratureRecord]:
        """Find RF-field candidates; this is explicitly not a complete graph."""
        if not self.settings.enable_candidate_citation_search:
            raise SourceUnavailable("candidate citation search is disabled in configuration")
        if "'" not in record.title:
            expression = f"RF='{record.title}'"
        elif '"' not in record.title:
            expression = f'RF="{record.title}"'
        else:
            raise SourceUnavailable(
                "title contains both quote types and cannot form a safe RF query"
            )
        service = self._ensure_service()
        try:
            from cnki_mcp.core.tools import professional_search  # type: ignore[import-untyped]

            results = service.worker.call(
                lambda page: professional_search.run_expression_on_page(
                    page,
                    expression,
                    sort_by="citation",
                    limit=limit,
                    max_pages=max(1, (limit + 19) // 20),
                )
            )
            rows = [
                {
                    "title": item.title,
                    "authors": list(item.authors),
                    "journal": item.journal,
                    "date": item.date,
                    "url": item.url or item.article_id,
                    "citation_count": item.citation_count,
                }
                for item in results
            ]
        except Exception as exc:
            raise SourceUnavailable(f"CNKI candidate-citation search failed: {exc}") from exc
        return [canonicalize_cnki(row) for row in rows]

    def download_pdf(
        self,
        detail_url: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> Any:
        """Use the authenticated browser to click an explicit PDF control."""
        service = self._ensure_service()
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = destination.with_suffix(destination.suffix + ".part")
        selectors = (
            "a:has-text('PDF下载')",
            "button:has-text('PDF下载')",
            "a[title*='PDF']",
            ".btn-dlpdf",
            "a[href*='download'][href*='pdf' i]",
        )

        def retrieve(page: Any) -> None:
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30_000)
            failures: list[str] = []
            for selector in selectors:
                locator = page.locator(selector)
                try:
                    count = min(locator.count(), 3)
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        text = (candidate.inner_text(timeout=2_000) or "").casefold()
                    except Exception:
                        text = ""
                    try:
                        href = candidate.get_attribute("href") or ""
                        title = candidate.get_attribute("title") or ""
                    except Exception:
                        href, title = "", ""
                    marker = " ".join((text, href.casefold(), title.casefold()))
                    if "pdf" not in marker:
                        continue
                    try:
                        with page.expect_download(timeout=30_000) as download_info:
                            candidate.click(timeout=10_000)
                        download_info.value.save_as(str(partial))
                        return
                    except Exception as exc:
                        failures.append(str(exc))
                        if href and not href.casefold().startswith("javascript:"):
                            try:
                                response = page.context.request.get(
                                    urljoin(page.url, href), timeout=60_000
                                )
                                if response.ok:
                                    body = response.body()
                                    if len(body) <= max_bytes:
                                        partial.write_bytes(body)
                                        return
                            except Exception as request_exc:
                                failures.append(str(request_exc))
            detail = "; ".join(failures[-3:])
            raise PdfValidationError(
                "no working explicit PDF download control was found"
                + (f": {detail}" if detail else "")
            )

        try:
            service.worker.call(retrieve)
            validate_pdf(partial, max_bytes=max_bytes)
            os.replace(partial, destination)
            return validate_pdf(destination, max_bytes=max_bytes)
        except PdfValidationError:
            raise
        except Exception as exc:
            raise PdfValidationError(f"CNKI browser PDF download failed: {exc}") from exc
        finally:
            partial.unlink(missing_ok=True)


__all__ = ["CnkiProvider", "canonicalize_cnki"]
