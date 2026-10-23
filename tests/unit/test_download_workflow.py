from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from agecon_literature_mcp.cnki import CnkiProvider
from agecon_literature_mcp.config import CnkiSettings
from agecon_literature_mcp.exceptions import PdfValidationError
from agecon_literature_mcp.pdf import download_direct_pdf, original_pdf_name, response_pdf_name


def test_filename_preservation_and_unsafe_names() -> None:
    assert original_pdf_name("合作社_作者.PDF") == "合作社_作者.PDF"
    assert (
        response_pdf_name("attachment; filename*=UTF-8''%E5%90%88%E4%BD%9C%E7%A4%BE.pdf")
        == "合作社.pdf"
    )
    for name in (None, "../a.pdf", "a\\b.pdf", "a.caj", "a", "a\x00.pdf"):
        with pytest.raises(PdfValidationError):
            original_pdf_name(name)


@pytest.mark.asyncio
async def test_download_keeps_server_name_and_separates_collisions(
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sample_pdf.read_bytes(),
            headers={
                "Content-Disposition": "attachment; filename=source.PDF",
                "Content-Type": "application/pdf",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await download_direct_pdf(
            "https://kns.cnki.net/file", tmp_path / "downloads", max_bytes=10000, client=client
        )
        second = await download_direct_pdf(
            "https://kns.cnki.net/file", tmp_path / "downloads", max_bytes=10000, client=client
        )
    assert first.path.name == second.path.name == "source.PDF"
    assert first.path != second.path
    assert first.sha256 == second.sha256


@pytest.mark.asyncio
async def test_missing_original_name_fails_without_inventing_pdf(tmp_path: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"<html>login</html>")
        )
    ) as client:
        with pytest.raises(PdfValidationError):
            await download_direct_pdf(
                "https://kns.cnki.net/file", tmp_path / "downloads", max_bytes=10000, client=client
            )
    assert not list(tmp_path.rglob("*.pdf"))


def test_browser_start_does_not_require_login(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    worker = SimpleNamespace(is_running=True, start=lambda **kw: calls.append(kw))
    service = SimpleNamespace(worker=worker)
    provider = CnkiProvider(CnkiSettings())
    # No auth object methods exist: the read startup cannot consult them.
    monkeypatch.setattr(provider, "_imports", lambda: (object(), lambda: service))
    assert provider._ensure_service() is service
    assert calls == [{"profile": "default"}]
    assert provider.last_download_access == {}


def test_access_signals_do_not_confuse_login_buttons_with_offcampus() -> None:
    classify = CnkiProvider._download_access_state
    assert (
        classify("https://www.cnki.net", "机构用户: 某大学")["status"] == "institution_recognized"
    )
    assert classify("https://www.cnki.net", "登录 注册 PDF下载")["status"] == "unknown"
    assert classify("https://fsso.cnki.net/login", "")["status"] == "institutional_login_required"


def test_browser_download_checks_access_then_preserves_original_filename(
    tmp_path: Path,
    sample_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import nullcontext

    events = []

    class Link:
        def count(self):
            return 1

        def nth(self, index):
            return self

        def inner_text(self, **kwargs):
            return "PDF下载"

        def get_attribute(self, name):
            return "https://kns.cnki.net/download/pdf"

        def click(self, **kwargs):
            events.append("download")

    class Page:
        url = "https://www.cnki.net/"

        def goto(self, url, **kwargs):
            self.url = url
            events.append(url)

        def locator(self, selector):
            if selector == "body":
                return SimpleNamespace(inner_text=lambda: "机构用户: 测试大学")
            return Link()

        def expect_download(self, **kwargs):
            return nullcontext(
                SimpleNamespace(
                    value=SimpleNamespace(
                        suggested_filename="原始题名_原始作者.pdf",
                        save_as=lambda filename: Path(filename).write_bytes(
                            sample_pdf.read_bytes()
                        ),
                    )
                )
            )

    page = Page()
    provider = CnkiProvider(CnkiSettings())
    monkeypatch.setattr(
        provider,
        "_ensure_service",
        lambda: SimpleNamespace(worker=SimpleNamespace(call=lambda fn: fn(page))),
    )
    artifact = provider.download_pdf(
        "https://kns.cnki.net/detail", tmp_path / "downloads", max_bytes=10000
    )
    assert events == ["https://www.cnki.net/", "https://kns.cnki.net/detail", "download"]
    assert artifact.path.name == "原始题名_原始作者.pdf"
    assert provider.last_download_access["status"] == "institution_recognized"


def test_download_login_redirect_requests_institutional_sso(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agecon_literature_mcp.exceptions import SetupRequired

    page = SimpleNamespace(
        url="https://fsso.cnki.net/login",
        goto=lambda *args, **kwargs: None,
        locator=lambda selector: SimpleNamespace(inner_text=lambda: "机构登录"),
    )
    provider = CnkiProvider(CnkiSettings())
    monkeypatch.setattr(
        provider,
        "_ensure_service",
        lambda: SimpleNamespace(worker=SimpleNamespace(call=lambda fn: fn(page))),
    )
    with pytest.raises(SetupRequired, match="SSO"):
        provider.download_pdf("https://kns.cnki.net/detail", tmp_path, max_bytes=10000)
    assert not list(tmp_path.rglob("*.pdf"))


def test_subscription_denial_does_not_request_sso(tmp_path: Path, monkeypatch) -> None:
    from agecon_literature_mcp.exceptions import SourceUnavailable

    page = SimpleNamespace(
        url="https://kns.cnki.net/detail",
        goto=lambda *args, **kwargs: None,
        locator=lambda selector: SimpleNamespace(
            inner_text=lambda: "机构用户: 测试大学 无下载权限 未订购",
            count=lambda: 0,
        ),
    )
    provider = CnkiProvider(CnkiSettings())
    monkeypatch.setattr(
        provider,
        "_ensure_service",
        lambda: SimpleNamespace(worker=SimpleNamespace(call=lambda fn: fn(page))),
    )
    with pytest.raises(SourceUnavailable, match="subscription"):
        provider.download_pdf("https://kns.cnki.net/detail", tmp_path, max_bytes=10000)
    assert not list(tmp_path.rglob("*.pdf"))
