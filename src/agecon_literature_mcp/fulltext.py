"""Local, content-addressed PDF text cache; extraction is not reading validation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pypdf


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def extract_cached(source: Path, cache_dir: Path) -> tuple[Path, dict[str, Any], bool]:
    """Cache numbered PDF pages by bytes, extractor version, and extraction schema."""
    raw = source.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise ValueError("source must be a PDF")
    identity = {
        "pdf_sha256": _digest(raw),
        "extractor": "pypdf",
        "extractor_version": pypdf.__version__,
        "schema": 1,
        "options": {"extraction_mode": "plain"},
    }
    destination = cache_dir / f"{_digest(_encoded(identity))}.json"
    try:
        cached = json.loads(destination.read_text(encoding="utf-8"))
        pages = cached["pages"]
        if (
            cached["identity"] == identity
            and isinstance(pages, list)
            and pages
            and all(
                isinstance(page, dict)
                and page.get("pdf_page") == i
                and isinstance(page.get("text"), str)
                for i, page in enumerate(pages, 1)
            )
            and cached["pages_sha256"] == _digest(_encoded(pages))
            and cached["validation_status"] == "extracted_not_visually_verified"
            and cached["payload_sha256"]
            == _digest(_encoded({k: v for k, v in cached.items() if k != "payload_sha256"}))
        ):
            return destination, cached, True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    reader = pypdf.PdfReader(io.BytesIO(raw))
    pages = [
        {"pdf_page": i, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages, 1)
    ]
    if not pages:
        raise ValueError("PDF has no pages")
    result = {
        "identity": identity,
        "pages": pages,
        "pages_sha256": _digest(_encoded(pages)),
        "validation_status": "extracted_not_visually_verified",
        "flags": {
            "empty_pages": [p["pdf_page"] for p in pages if not p["text"].strip()],
            "replacement_character_pages": [p["pdf_page"] for p in pages if "\ufffd" in p["text"]],
        },
    }
    result["payload_sha256"] = _digest(_encoded(result))
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(_encoded(result))
        os.replace(temp_path, destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return destination, result, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--start-page", type=int)
    parser.add_argument("--end-page", type=int)
    args = parser.parse_args()
    if args.end_page is not None and args.start_page is None:
        parser.error("--end-page requires --start-page")
    path, result, hit = extract_cached(args.pdf, args.cache_dir)
    pages = result["pages"]
    if args.start_page is not None:
        end = args.end_page if args.end_page is not None else args.start_page
        if not 1 <= args.start_page <= end <= len(pages):
            parser.error("page range must be within the PDF")
        print(json.dumps(pages[args.start_page - 1 : end], ensure_ascii=False))
    else:
        print(
            json.dumps(
                {
                    "cache_path": str(path),
                    "cache_hit": hit,
                    "page_count": len(pages),
                    "flags": result["flags"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
