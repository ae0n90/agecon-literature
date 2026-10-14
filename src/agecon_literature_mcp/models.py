"""Canonical records, evidence flags, and operation state models."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def normalize_space(value: str | None) -> str | None:
    """Normalize Unicode width and whitespace without translating content."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_title(value: str) -> str:
    """Return a conservative title key for exact-ish duplicate matching."""
    normalized = normalize_space(value) or ""
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE).casefold()


def normalize_doi(value: str | None) -> str | None:
    """Strip resolver prefixes and normalize a DOI for equality checks."""
    normalized = normalize_space(re.sub(r"[\ufeff\u200b-\u200d\u2060]", "", value or ""))
    if not normalized:
        return None
    normalized = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", normalized, flags=re.I)
    return normalized.rstrip(". ").casefold() or None


def stable_id(
    source: str,
    source_id: str | None,
    title: str,
    authors: list[str],
    year: int | None,
) -> str:
    """Create a deterministic, non-secret identifier for one literature record."""
    identity = source_id or "|".join(
        [normalize_title(title), normalize_title(authors[0]) if authors else "", str(year or "")]
    )
    digest = hashlib.sha256(f"{source}\0{identity}".encode()).hexdigest()[:24]
    return f"{source}-{digest}"


class EvidenceLevel(StrEnum):
    """Highest source layer directly inspected for a record."""

    SEARCH_RESULT = "search_result"
    METADATA = "metadata"
    ABSTRACT = "abstract"
    FULL_TEXT = "full_text"


class RelationCompleteness(StrEnum):
    """How completely a reported paper relation is known."""

    UNAVAILABLE = "unavailable"
    CANDIDATE = "candidate"
    PARTIAL = "partial"
    COMPLETE = "complete"


class LiteratureRecord(BaseModel):
    """Source-preserving canonical metadata for a paper-like item."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str = "cnki"
    source_id: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1000, le=2200)
    source_title: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    download_url: str | None = None
    citation_count: int | None = Field(default=None, ge=0)
    evidence_level: EvidenceLevel = EvidenceLevel.SEARCH_RESULT
    retrieved_at: datetime = Field(default_factory=utc_now)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        normalized = normalize_space(value)
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized

    @field_validator("authors", "institutions", "keywords")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized = [normalize_space(value) for value in values]
        return list(dict.fromkeys(value for value in normalized if value))

    @field_validator("doi", mode="before")
    @classmethod
    def canonical_doi(cls, value: object) -> object:
        return normalize_doi(value) if isinstance(value, str) else value

    @property
    def title_key(self) -> str:
        return normalize_title(self.title)

    @property
    def first_author_key(self) -> str:
        return normalize_title(self.authors[0]) if self.authors else ""

    @property
    def fingerprint(self) -> str:
        """Hash metadata used to reject stale plans after record changes."""
        payload = self.model_dump_json(exclude={"retrieved_at", "raw"})
        return hashlib.sha256(payload.encode()).hexdigest()


class SearchSpec(BaseModel):
    """Persisted, exactly replayable search request."""

    model_config = ConfigDict(extra="forbid")

    query: str
    field: str = "topic"
    year_from: int | None = None
    year_to: int | None = None
    journal: str | None = None
    source_types: list[str] = Field(default_factory=list)
    sort_by: str = "relevance"
    limit: int = Field(default=20, ge=1, le=500)


class ImportMode(StrEnum):
    """Supported, intentionally narrow Zotero import modes."""

    METADATA_ONLY = "metadata_only"
    METADATA_WITH_PDF = "metadata_with_pdf"
    ATTACH_PDF_TO_EXISTING = "attach_pdf_to_existing"


class PlanKind(StrEnum):
    """Mutation plan classes."""

    PDF_DOWNLOAD = "pdf_download"
    ZOTERO_IMPORT = "zotero_import"
    ZOTERO_RESUME = "zotero_resume"


class PlanState(StrEnum):
    """Lifecycle of a short-lived, confirmable plan."""

    PLANNED = "planned"
    COMMITTED = "committed"
    EXPIRED = "expired"
    FAILED = "failed"


class OperationState(StrEnum):
    """Persisted non-atomic Zotero import states."""

    PLANNED = "planned"
    METADATA_CREATED = "metadata_created"
    ATTACHMENT_CREATED = "attachment_created"
    BYTES_UPLOADED = "bytes_uploaded"
    UPLOAD_REGISTERED = "upload_registered"
    VERIFIED = "verified"
    COMPLETE = "complete"
    RECOVERABLE_FAILED = "recoverable_failed"


class PdfArtifact(BaseModel):
    """Validated local PDF facts used for deduplication and upload."""

    model_config = ConfigDict(extra="forbid")

    path: Path
    sha256: str
    md5: str
    size_bytes: int = Field(ge=1)
    mtime_ms: int = Field(ge=0)
    pages: int = Field(ge=1)


class MatchKind(StrEnum):
    """Zotero duplicate-match confidence classes."""

    NONE = "none"
    DOI_EXACT = "doi_exact"
    SOURCE_KEY_EXACT = "source_key_exact"
    TITLE_AUTHOR_YEAR_EXACT = "title_author_year_exact"
    TITLE_CANDIDATE = "title_candidate"


class ZoteroMatch(BaseModel):
    """One read-only candidate match in the current Zotero library."""

    model_config = ConfigDict(extra="forbid")

    item_key: str
    kind: MatchKind
    title: str
    creators: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    score: float = Field(default=0.0, ge=0, le=1)


__all__ = [
    "EvidenceLevel",
    "ImportMode",
    "LiteratureRecord",
    "MatchKind",
    "OperationState",
    "PdfArtifact",
    "PlanKind",
    "PlanState",
    "RelationCompleteness",
    "SearchSpec",
    "ZoteroMatch",
    "normalize_doi",
    "normalize_space",
    "normalize_title",
    "stable_id",
    "utc_now",
]
