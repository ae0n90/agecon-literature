from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import httpx

from agecon_literature_mcp.config import ZoteroSettings
from agecon_literature_mcp.models import LiteratureRecord
from agecon_literature_mcp.pdf import validate_pdf
from agecon_literature_mcp.zotero import ZoteroLocalClient


class MemoryKeyStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, server_id: str) -> str | None:
        return self.values.get(server_id)

    def set(self, server_id: str, key: str) -> None:
        self.values[server_id] = key

    def delete(self, server_id: str) -> None:
        self.values.pop(server_id, None)


def test_authorization_and_item_creation_use_official_local_headers() -> None:
    key_store = MemoryKeyStore()
    seen_write = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_write
        headers = {
            "Zotero-Server-ID": "SERVER1",
            "Zotero-API-Version": "3",
            "Zotero-Schema-Version": "44",
        }
        if request.method == "GET" and request.url.path == "/api/":
            return httpx.Response(200, headers=headers, text="Zotero")
        if request.url.path == "/api/local/authorize":
            assert request.headers["Zotero-Server-ID"] == "SERVER1"
            return httpx.Response(
                200,
                headers=headers,
                json={"key": "K" * 32, "remember": True},
            )
        if request.url.path == "/api/users/0/items":
            seen_write = True
            assert request.headers["Zotero-Server-ID"] == "SERVER1"
            assert request.headers["Zotero-API-Key"] == "K" * 32
            assert len(request.headers["Zotero-Write-Token"]) == 32
            return httpx.Response(
                200,
                headers=headers,
                json={"successful": {"0": {"key": "ABCD2345"}}, "failed": {}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    zotero = ZoteroLocalClient(ZoteroSettings(), key_store=key_store, client=http)
    result = zotero.authorize_writes()
    assert result["remembered"] is True
    key = zotero.create_item(
        {"itemType": "journalArticle", "title": "Test"},
        expected_server_id="SERVER1",
    )
    assert key == "ABCD2345"
    assert seen_write


def test_default_client_never_uses_environment_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class ClientStub:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr("agecon_literature_mcp.zotero.httpx.Client", ClientStub)
    zotero = ZoteroLocalClient(ZoteroSettings(), key_store=MemoryKeyStore())
    zotero.close()
    assert captured["trust_env"] is False


def test_full_pdf_upload_has_three_persistable_protocol_phases(sample_pdf: Path) -> None:
    artifact = validate_pdf(sample_pdf, max_bytes=1_000_000)
    key_store = MemoryKeyStore()
    key_store.set("SERVER1", "K" * 32)
    phases: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Zotero-Server-ID": "SERVER1", "Zotero-API-Version": "3"}
        if request.method == "GET" and request.url.path == "/api/":
            return httpx.Response(200, headers=headers, text="Zotero")
        if request.url.path == "/api/users/0/items/ATCH2345/file":
            form = parse_qs(request.content.decode())
            assert request.headers["If-None-Match"] == "*"
            if "md5" in form:
                phases.append("authorize")
                assert form["md5"] == [artifact.md5]
                return httpx.Response(
                    200,
                    headers=headers,
                    json={
                        "url": "/api/local/uploads/UPLOAD1",
                        "uploadKey": "UPLOAD1",
                        "contentType": "application/pdf",
                    },
                )
            phases.append("register")
            assert form["upload"] == ["UPLOAD1"]
            return httpx.Response(204, headers=headers)
        if request.url.path == "/api/local/uploads/UPLOAD1":
            phases.append("bytes")
            assert request.content == sample_pdf.read_bytes()
            return httpx.Response(201)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    zotero = ZoteroLocalClient(ZoteroSettings(), key_store=key_store, client=http)
    authorization = zotero.authorize_attachment_upload(
        "ATCH2345", artifact, expected_server_id="SERVER1"
    )
    zotero.upload_attachment_bytes(authorization, artifact)
    zotero.register_attachment_upload(
        "ATCH2345", authorization["upload_key"], expected_server_id="SERVER1"
    )
    assert phases == ["authorize", "bytes", "register"]


def test_attachment_verification_ignores_renamed_file(sample_pdf: Path) -> None:
    artifact = validate_pdf(sample_pdf, max_bytes=1_000_000)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/items/ATCH2345"
        data = {"key": "ATCH2345", "md5": artifact.md5, "filename": "2007-作者 等-题名.pdf"}
        return httpx.Response(200, json={"key": "ATCH2345", "data": data})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    zotero = ZoteroLocalClient(ZoteroSettings(), key_store=MemoryKeyStore(), client=http)
    assert zotero.verify_attachment("ATCH2345", artifact)


def test_match_keeps_fuzzy_candidate_separate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Zotero-Server-ID": "SERVER1", "Zotero-API-Version": "3"}
        if request.url.path == "/api/":
            return httpx.Response(200, headers=headers, text="Zotero")
        if request.url.path == "/api/users/0/items/top":
            return httpx.Response(
                200,
                headers=headers,
                json=[
                    {
                        "key": "ABCD2345",
                        "data": {
                            "title": "农业社会化服务与粮食生产效率研究",
                            "creators": [{"name": "张三"}],
                            "date": "2024",
                            "DOI": "",
                            "extra": "",
                        },
                    }
                ],
            )
        raise AssertionError(str(request.url))

    zotero = ZoteroLocalClient(
        ZoteroSettings(),
        key_store=MemoryKeyStore(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    record = LiteratureRecord(
        id="cnki-1",
        title="农业社会化服务与粮食生产效率",
        authors=["张三"],
        year=2024,
    )
    matches = zotero.match(record)
    assert matches[0].kind.value == "title_candidate"


def test_doi_and_source_id_matching_use_everything_mode() -> None:
    observed_modes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Zotero-Server-ID": "SERVER1", "Zotero-API-Version": "3"}
        if request.url.path == "/api/users/0/items/top":
            observed_modes.append(request.url.params["qmode"])
            return httpx.Response(
                200,
                headers=headers,
                json=[
                    {
                        "key": "ABCD2345",
                        "data": {
                            "title": "农业服务",
                            "creators": [{"name": "张三"}],
                            "date": "2024",
                            "DOI": "10.1234/example",
                            "extra": "CNKI-ID: CJFD:ABC",
                        },
                    }
                ],
            )
        raise AssertionError(str(request.url))

    zotero = ZoteroLocalClient(
        ZoteroSettings(),
        key_store=MemoryKeyStore(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    matches = zotero.match(
        LiteratureRecord(
            id="cnki-1",
            source_id="CJFD:ABC",
            title="农业服务",
            authors=["张三"],
            year=2024,
            doi="10.1234/example",
        )
    )
    assert matches[0].kind.value == "doi_exact"
    assert observed_modes == ["everything", "everything", "titleCreatorYear"]


def test_recovery_search_includes_plugin_reparented_attachments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/items"
        assert "itemType" not in request.url.params
        return httpx.Response(
            200, json=[{"key": "ATCH2345", "data": {"parentItem": "PLUGIN23", "note": "op-test"}}]
        )

    client = ZoteroLocalClient(
        ZoteroSettings(),
        key_store=MemoryKeyStore(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.find_by_operation_marker("op-test")[0]["key"] == "ATCH2345"


def test_metadata_assessment_separates_identity_and_completeness():
    from agecon_literature_mcp.zotero import assess_metadata

    record = LiteratureRecord(id="test", title="合作社", authors=["张三"], year=2024)
    data = {
        "itemType": "thesis",
        "title": "合作社",
        "date": "2024",
        "creators": [
            {"creatorType": "contributor", "name": "导师"},
            {"creatorType": "author", "name": "张三"},
        ],
    }
    assert assess_metadata(record, data)["identity_status"] == "matched"
    assert assess_metadata(record, data)["missing_fields"] == ["university"]
    data["date"] = "2023"
    assert assess_metadata(record, data)["identity_conflicts"] == ["year"]
    del data["date"]
    assert assess_metadata(record, data)["identity_status"] == "incomplete"


def test_incomplete_title_matches_are_not_exact():
    from agecon_literature_mcp.models import MatchKind
    from agecon_literature_mcp.service import LiteratureService

    record = LiteratureRecord(id="test", title="合作社", authors=["张三"], year=2024)
    data = {"title": "合作社", "creators": [{"name": "张三"}]}

    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json=[{"key": "ITEM2345", "data": data}])

    client = ZoteroLocalClient(
        ZoteroSettings(),
        key_store=MemoryKeyStore(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    matches = client.match(record)
    assert matches[0].kind == MatchKind.TITLE_METADATA_INCOMPLETE
    assert LiteratureService._exact_matches(matches) == []
    data["date"] = "2024"
    assert client.match(record)[0].kind == MatchKind.TITLE_AUTHOR_YEAR_EXACT
    data["creators"] = [{"creatorType": "contributor", "name": "张三"}]
    assert client.match(record)[0].kind == MatchKind.TITLE_METADATA_INCOMPLETE

    data["creators"] = [{"name": "张三"}]
    record.authors = []
    assert client.match(record)[0].kind == MatchKind.TITLE_METADATA_INCOMPLETE
    record.authors = ["李四"]
    assert client.match(record)[0].kind == MatchKind.TITLE_CANDIDATE
