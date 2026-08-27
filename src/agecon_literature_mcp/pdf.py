"""PDF-only download validation and artifact metadata."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

from .exceptions import PdfValidationError
from .models import PdfArtifact


def safe_filename(title: str, suffix: str = ".pdf", max_stem: int = 120) -> str:
    """Create a filesystem-safe name without losing the human-readable title."""
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._") or "document"
    return f"{cleaned[:max_stem].rstrip()}{suffix}"


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pdf(path: Path, *, max_bytes: int) -> PdfArtifact:
    """Verify signature, size, parseability, hashes, and at least one page."""
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise PdfValidationError(f"not a regular file: {resolved}")
    size = resolved.stat().st_size
    if size < 8:
        raise PdfValidationError("file is too small to be a PDF")
    if size > max_bytes:
        raise PdfValidationError(f"PDF exceeds configured limit: {size} > {max_bytes}")
    with resolved.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise PdfValidationError("file does not begin with a PDF signature")
    try:
        reader = PdfReader(resolved, strict=False)
        page_count = len(reader.pages)
    except Exception as exc:
        raise PdfValidationError(f"PDF parser rejected the file: {exc}") from exc
    if page_count < 1:
        raise PdfValidationError("PDF contains no pages")
    stat = resolved.stat()
    return PdfArtifact(
        path=resolved,
        sha256=_hash_file(resolved, "sha256"),
        # MD5 is required by Zotero's upload protocol; SHA-256 is retained too.
        md5=_hash_file(resolved, "md5"),
        size_bytes=size,
        mtime_ms=stat.st_mtime_ns // 1_000_000,
        pages=page_count,
    )


def is_cnki_url(url: str) -> bool:
    """Allow only HTTPS CNKI hosts for direct full-text retrieval."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and (hostname == "cnki.net" or hostname.endswith(".cnki.net"))


async def download_direct_pdf(
    url: str,
    destination: Path,
    *,
    max_bytes: int,
    client: httpx.AsyncClient | None = None,
) -> PdfArtifact:
    """Download a direct CNKI PDF URL and reject HTML, CAJ, or oversized bytes."""
    if not is_cnki_url(url):
        raise PdfValidationError("download URL must be an HTTPS cnki.net URL")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = destination.with_suffix(destination.suffix + ".part")
    owns_client = client is None
    http = client or httpx.AsyncClient(follow_redirects=True, timeout=60)
    try:
        async with http.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").casefold()
            if "text/html" in content_type or "application/json" in content_type:
                raise PdfValidationError(f"server returned {content_type or 'non-PDF content'}")
            written = 0
            with partial.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    written += len(chunk)
                    if written > max_bytes:
                        raise PdfValidationError("download exceeded the configured PDF size limit")
                    handle.write(chunk)
        validate_pdf(partial, max_bytes=max_bytes)
        os.replace(partial, destination)
        return validate_pdf(destination, max_bytes=max_bytes)
    finally:
        partial.unlink(missing_ok=True)
        if owns_client:
            await http.aclose()


__all__ = ["download_direct_pdf", "is_cnki_url", "safe_filename", "validate_pdf"]
