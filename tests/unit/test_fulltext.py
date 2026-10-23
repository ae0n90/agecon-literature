import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from agecon_literature_mcp import fulltext


def test_cache_reuses_identical_bytes_and_repairs_corruption(tmp_path: Path, sample_pdf: Path):
    cache = tmp_path / "cache"
    path, result, hit = fulltext.extract_cached(sample_pdf, cache)
    assert not hit
    renamed = tmp_path / "original.pdf"
    renamed.write_bytes(sample_pdf.read_bytes())
    assert fulltext.extract_cached(renamed, cache) == (path, result, True)
    path.write_text('{"pages": []}')
    assert not fulltext.extract_cached(renamed, cache)[2]
    assert fulltext.extract_cached(renamed, cache)[2]
    corrupted = json.loads(path.read_text())
    corrupted["pages"][0]["text"] = "wrong text"
    path.write_text(json.dumps(corrupted))
    assert not fulltext.extract_cached(renamed, cache)[2]
    original = renamed.read_bytes()
    renamed.write_bytes(original + b"\n% modified\n")
    assert fulltext.extract_cached(renamed, cache)[0] != path


def test_cache_version_and_extraction_failure(tmp_path: Path, sample_pdf: Path, monkeypatch):
    cache = tmp_path / "cache"
    path, _, _ = fulltext.extract_cached(sample_pdf, cache)
    monkeypatch.setattr(fulltext.pypdf, "__version__", "test-next")
    assert fulltext.extract_cached(sample_pdf, cache)[0] != path
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-broken")
    before = set(cache.iterdir())
    with pytest.raises(PdfReadError):
        fulltext.extract_cached(bad, cache)
    assert set(cache.iterdir()) == before


def test_cache_marks_empty_pages_not_verified(tmp_path: Path):
    source = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(source)
    _, result, _ = fulltext.extract_cached(source, tmp_path / "cache")
    assert result["pages"][0]["pdf_page"] == 1
    assert result["flags"]["empty_pages"] == [1]
    assert result["validation_status"] == "extracted_not_visually_verified"
