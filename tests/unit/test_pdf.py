from pathlib import Path

import pytest

from agecon_literature_mcp.exceptions import PdfValidationError
from agecon_literature_mcp.pdf import safe_filename, validate_pdf


def test_validate_pdf_computes_both_hashes(sample_pdf: Path) -> None:
    artifact = validate_pdf(sample_pdf, max_bytes=1_000_000)
    assert artifact.pages == 1
    assert len(artifact.sha256) == 64
    assert len(artifact.md5) == 32


def test_validate_pdf_rejects_login_html(tmp_path: Path) -> None:
    fake = tmp_path / "paper.pdf"
    fake.write_text("<html>请登录</html>", encoding="utf-8")
    with pytest.raises(PdfValidationError, match="signature"):
        validate_pdf(fake, max_bytes=1_000_000)


def test_safe_filename_removes_path_controls() -> None:
    assert safe_filename('A/B: C? "D"') == "A_B_ C_ _D.pdf"
