from __future__ import annotations

from pathlib import Path

import pytest

from agecon_literature_mcp.config import Settings
from agecon_literature_mcp.exceptions import SourceUnavailable
from agecon_literature_mcp.models import LiteratureRecord, SearchSpec
from agecon_literature_mcp.service import LiteratureService
from agecon_literature_mcp.storage import Ledger


class SearchCnki:
    def __init__(self, records: list[LiteratureRecord]) -> None:
        self.records = records

    def search(self, spec: SearchSpec) -> list[LiteratureRecord]:
        assert spec.query
        return self.records

    def close(self) -> None:
        return


class SearchZotero:
    def close(self) -> None:
        return


def _service(tmp_path: Path, records: list[LiteratureRecord]) -> LiteratureService:
    settings = Settings(runtime={"data_dir": tmp_path / "runtime"})
    return LiteratureService(
        settings,
        ledger=Ledger(settings.database_path),
        cnki=SearchCnki(records),  # type: ignore[arg-type]
        zotero=SearchZotero(),  # type: ignore[arg-type]
    )


def test_search_deduplicates_identical_results(tmp_path: Path) -> None:
    record = LiteratureRecord(
        id="cnki-same",
        title="农业社会化服务",
        authors=["张三"],
        year=2024,
    )
    service = _service(tmp_path, [record, record.model_copy()])
    result = service.lit_search("农业社会化服务")
    assert result["count"] == 1
    assert service.lit_session_summary(result["session_id"])["record_count"] == 1


def test_search_rejects_distinct_records_with_same_id(tmp_path: Path) -> None:
    records = [
        LiteratureRecord(id="cnki-collision", title="第一篇", authors=["张三"], year=2024),
        LiteratureRecord(id="cnki-collision", title="第二篇", authors=["李四"], year=2023),
    ]
    service = _service(tmp_path, records)
    with pytest.raises(SourceUnavailable, match="distinct records"):
        service.lit_search("农业社会化服务")
