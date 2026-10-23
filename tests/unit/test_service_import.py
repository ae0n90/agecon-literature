from __future__ import annotations

from pathlib import Path
from typing import Any

from agecon_literature_mcp.config import Settings
from agecon_literature_mcp.models import LiteratureRecord, OperationState
from agecon_literature_mcp.pdf import validate_pdf
from agecon_literature_mcp.service import LiteratureService
from agecon_literature_mcp.storage import Ledger
from agecon_literature_mcp.zotero import ZoteroLocalClient


class FakeCnki:
    def close(self) -> None:
        return


class FakeZotero:
    def __init__(self, *, fail_register_once: bool = False) -> None:
        self.parents: dict[str, dict[str, Any]] = {}
        self.attachments: dict[str, dict[str, Any]] = {}
        self.fail_register_once = fail_register_once
        self.register_attempts = 0
        self.upload_attempts = 0

    def close(self) -> None:
        return

    def probe(self) -> dict[str, Any]:
        return {"server_id": "SERVER1", "available": True}

    def validate_collection(self, collection_key: str | None) -> None:
        self.validated_collection = collection_key

    def match(self, record: LiteratureRecord) -> list[Any]:
        return []

    def child_items(self, parent_key: str) -> list[dict[str, Any]]:
        return [
            {"key": key, "data": value}
            for key, value in self.attachments.items()
            if value.get("parentItem") == parent_key
        ]

    def find_by_operation_marker(self, operation_id: str) -> list[dict[str, Any]]:
        return [
            {"key": key, "data": value}
            for key, value in (self.parents | self.attachments).items()
            if operation_id in value.get("extra", "") or operation_id in value.get("note", "")
        ]

    item_payload = staticmethod(ZoteroLocalClient.item_payload)
    attachment_payload = staticmethod(ZoteroLocalClient.attachment_payload)

    def create_item(self, payload: dict[str, Any], *, expected_server_id: str) -> str:
        assert expected_server_id == "SERVER1"
        if payload["itemType"] == "attachment":
            key = "ATCH2345"
            self.attachments[key] = payload.copy()
            return key
        key = "PARN2345"
        self.parents[key] = payload.copy()
        return key

    def get_item(self, item_key: str) -> dict[str, Any]:
        if item_key in self.parents:
            return {"key": item_key, "data": self.parents[item_key]}
        return {"key": item_key, "data": self.attachments[item_key]}

    def authorize_attachment_upload(
        self,
        attachment_key: str,
        artifact: Any,
        *,
        expected_server_id: str,
    ) -> dict[str, Any]:
        return {
            "exists": False,
            "upload_url": "http://127.0.0.1/upload",
            "upload_key": f"UPLOAD{self.upload_attempts + 1}",
            "content_type": "application/pdf",
        }

    def upload_attachment_bytes(self, authorization: dict[str, Any], artifact: Any) -> None:
        self.upload_attempts += 1

    def register_attachment_upload(
        self,
        attachment_key: str,
        upload_key: str,
        *,
        expected_server_id: str,
    ) -> None:
        self.register_attempts += 1
        if self.fail_register_once and self.register_attempts == 1:
            raise RuntimeError("simulated interrupted registration")
        attachment = self.attachments[attachment_key]
        attachment["md5"] = self.current_artifact.md5

    def verify_attachment(self, attachment_key: str, artifact: Any) -> bool:
        self.current_artifact = artifact
        attachment = self.attachments[attachment_key]
        # A successful fake registration on resume sets md5 just before verification.
        if self.register_attempts and not (self.fail_register_once and self.register_attempts == 1):
            attachment["md5"] = artifact.md5
        return bool(attachment.get("md5") == artifact.md5)


def _service(tmp_path: Path, fake_zotero: FakeZotero) -> LiteratureService:
    settings = Settings(runtime={"data_dir": tmp_path / "runtime"})
    ledger = Ledger(settings.database_path)
    service = LiteratureService(
        settings,
        ledger=ledger,
        cnki=FakeCnki(),  # type: ignore[arg-type]
        zotero=fake_zotero,  # type: ignore[arg-type]
    )
    ledger.upsert_record(
        LiteratureRecord(
            id="cnki-1",
            source_id="CNKI-ONE",
            title="农业服务市场竞争与生产效率",
            authors=["张三"],
            year=2024,
        )
    )
    return service


def test_single_allowlisted_collection_is_default_target(tmp_path: Path) -> None:
    fake = FakeZotero()
    service = _service(tmp_path, fake)
    service.settings.zotero.allow_root_library = False
    service.settings.zotero.allowed_collections = ["INBOX123"]
    plan = service.zotero_plan_import(["cnki-1"], mode="metadata_only")
    assert fake.validated_collection == "INBOX123"
    assert plan["items"][0]["collection_key"] == "INBOX123"


def test_metadata_only_plan_and_commit_complete(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeZotero())
    plan = service.zotero_plan_import(["cnki-1"], mode="metadata_only")
    assert plan["items"][0]["action"] == "create_metadata"
    committed = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    assert committed["complete"] is True
    assert committed["operations"][0]["state"] == OperationState.COMPLETE.value


def test_pdf_import_recovers_after_registration_failure(
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    fake = FakeZotero(fail_register_once=True)
    service = _service(tmp_path, fake)
    artifact = validate_pdf(sample_pdf, max_bytes=1_000_000)
    fake.current_artifact = artifact
    plan = service.zotero_plan_import(
        ["cnki-1"],
        mode="metadata_with_pdf",
        pdf_paths={"cnki-1": str(sample_pdf)},
    )
    first = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    operation = first["operations"][0]
    assert operation["state"] == OperationState.RECOVERABLE_FAILED.value
    assert operation["payload"]["last_successful_state"] == OperationState.BYTES_UPLOADED.value

    resume_plan = service.zotero_plan_resume(operation["id"])
    resumed = service.zotero_resume_import(
        resume_plan["plan_id"], resume_plan["confirmation_token"]
    )
    assert resumed["state"] == OperationState.COMPLETE.value
    assert fake.upload_attempts == 2
    assert fake.register_attempts == 2


def test_known_thesis_is_not_forced_into_journal_article(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeZotero())
    service.ledger.upsert_record(
        LiteratureRecord(
            id="cnki-thesis",
            source_id="CMFD:THESIS001",
            title="农业服务学位论文",
            authors=["李四"],
            year=2023,
        )
    )
    plan = service.zotero_plan_import(["cnki-thesis"], mode="metadata_only")
    assert plan["status"] == "conflict"
    assert "thesis" in plan["conflicts"][0]["reason"]


def test_default_pdf_import_does_not_create_bibliographic_parent(
    tmp_path: Path,
    sample_pdf: Path,
) -> None:
    original = tmp_path / "合作社组织研究_张三.PDF"
    original.write_bytes(sample_pdf.read_bytes())
    fake = FakeZotero()
    fake.current_artifact = validate_pdf(original, max_bytes=1_000_000)
    service = _service(tmp_path, fake)
    plan = service.zotero_plan_import(["cnki-1"], pdf_paths={"cnki-1": str(original)})
    assert plan["items"][0]["action"] == "create_standalone_pdf"
    result = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    assert result["complete"]
    assert fake.parents == {}
    attachment = fake.attachments["ATCH2345"]
    assert "parentItem" not in attachment
    assert attachment["title"] == attachment["filename"] == original.name
    assert not any(k in attachment for k in ("creators", "date", "publicationTitle"))
    operation = result["operations"][0]["id"]
    verification = service.zotero_verify_import(operation)
    assert verification["verified"]
    assert verification["metadata_status"] == "pending_plugin"
    assert verification["checks"]["original_filename_preserved"]
    assert verification["attachment_key"] == "ATCH2345"
    assert verification["stored_filename"] == original.name
    # Observe and assess plugin metadata without rewriting it.
    fake.parents["PLUGIN23"] = {"title": "合作社组织研究", "issue": "10", "pages": "79-88"}
    attachment["parentItem"] = "PLUGIN23"
    verification = service.zotero_verify_import(operation)
    assert verification["metadata_status"] == "parent_created"
    assert verification["metadata"]["pages"] == "79-88"
    assert verification["metadata_assessment"]["identity_status"] == "conflict"
    assert "date" in verification["metadata_assessment"]["missing_fields"]
    assert verification["checks"]["single_expected_pdf"]
    fake.attachments["EXTRA234"] = dict(attachment)
    duplicate_check = service.zotero_verify_import(operation)
    assert duplicate_check["checks"]["pdf_attachment_count"] == 2
    assert not duplicate_check["checks"]["single_expected_pdf"]
    del fake.attachments["EXTRA234"]
    assert "date" not in fake.parents["PLUGIN23"]  # Never fill missing plugin fields.
    # A subsequent plugin rename must be reported without rewriting the item or
    # confusing a filename change with damaged bytes.
    attachment["filename"] = "插件重命名.pdf"
    verification = service.zotero_verify_import(operation)
    assert verification["verified"]
    assert not verification["checks"]["original_filename_preserved"]
    assert verification["original_filename"] == original.name
    assert verification["stored_filename"] == "插件重命名.pdf"
    assert len(fake.attachments) == len(fake.parents) == 1


def test_legacy_new_pdf_request_uses_standalone_mode(tmp_path: Path, sample_pdf: Path) -> None:
    service = _service(tmp_path, FakeZotero())
    plan = service.zotero_plan_import(
        ["cnki-1"], mode="metadata_with_pdf", pdf_paths={"cnki-1": str(sample_pdf)}
    )
    assert plan["items"][0]["action"] == "create_standalone_pdf"
    assert plan["items"][0]["mode"] == "standalone_pdf"


def test_standalone_resume_after_plugin_reparenting(tmp_path: Path, sample_pdf: Path) -> None:
    fake = FakeZotero(fail_register_once=True)
    fake.current_artifact = validate_pdf(sample_pdf, max_bytes=1_000_000)
    service = _service(tmp_path, fake)
    plan = service.zotero_plan_import(["cnki-1"], pdf_paths={"cnki-1": str(sample_pdf)})
    first = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    operation = first["operations"][0]
    assert operation["state"] == "recoverable_failed"
    fake.parents["PLUGIN23"] = {"title": "插件规范化后的标题"}
    fake.attachments["ATCH2345"]["parentItem"] = "PLUGIN23"
    resume = service.zotero_plan_resume(operation["id"])
    result = service.zotero_resume_import(resume["plan_id"], resume["confirmation_token"])
    assert result["state"] == "complete"
    assert len(fake.attachments) == len(fake.parents) == 1
    assert fake.attachments["ATCH2345"]["parentItem"] == "PLUGIN23"


def test_incomplete_match_uses_existing_conflict_path(tmp_path: Path, sample_pdf: Path):
    from agecon_literature_mcp.models import MatchKind, ZoteroMatch

    class IncompleteMatchZotero(FakeZotero):
        def match(self, record):
            return [
                ZoteroMatch(
                    item_key="ITEM2345",
                    title=record.title,
                    kind=MatchKind.TITLE_METADATA_INCOMPLETE,
                    score=0.9,
                )
            ]

    fake = IncompleteMatchZotero()
    service = _service(tmp_path, fake)
    plan = service.zotero_plan_import(["cnki-1"], pdf_paths={"cnki-1": str(sample_pdf)})
    assert plan["conflicts"]
    assert not plan["safe_items"]
    assert not plan["committable"]
    assert not fake.parents and not fake.attachments


def test_metadata_commit_stops_on_new_incomplete_candidate(tmp_path: Path, monkeypatch):
    from agecon_literature_mcp.models import MatchKind, ZoteroMatch

    fake = FakeZotero()
    service = _service(tmp_path, fake)
    plan = service.zotero_plan_import(["cnki-1"], mode="metadata_only")
    monkeypatch.setattr(
        fake,
        "match",
        lambda record: [
            ZoteroMatch(
                item_key="ITEM2345",
                title=record.title,
                kind=MatchKind.TITLE_METADATA_INCOMPLETE,
                score=0.9,
            )
        ],
    )
    result = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    assert not result["complete"]
    assert not fake.parents and not fake.attachments


def test_metadata_recovery_rejects_ambiguous_markers(tmp_path: Path, monkeypatch):
    fake = FakeZotero()
    service = _service(tmp_path, fake)
    plan = service.zotero_plan_import(["cnki-1"], mode="metadata_only")
    monkeypatch.setattr(
        fake,
        "find_by_operation_marker",
        lambda operation_id: [{"key": "FIRST234"}, {"key": "SECOND23"}],
    )
    result = service.zotero_commit_import(plan["plan_id"], plan["confirmation_token"])
    assert not result["complete"]
    assert not fake.parents and not fake.attachments
