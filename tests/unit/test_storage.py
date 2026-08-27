from pathlib import Path

import pytest

from agecon_literature_mcp.exceptions import InvalidPlan
from agecon_literature_mcp.models import LiteratureRecord, PlanKind, PlanState, SearchSpec
from agecon_literature_mcp.storage import Ledger


def test_session_record_roundtrip(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    spec = SearchSpec(query="农业社会化服务")
    session_id = ledger.create_session(spec)
    record = LiteratureRecord(id="cnki-1", title="示例", authors=["周某"], year=2025)
    ledger.upsert_record(record)
    ledger.add_session_records(session_id, [record])
    loaded = ledger.get_records(session_id=session_id)
    assert loaded == [record]
    assert ledger.get_session(session_id)["spec"]["query"] == "农业社会化服务"


def test_plan_token_is_exact_and_single_use(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    plan_id, token, _ = ledger.create_plan(
        PlanKind.PDF_DOWNLOAD,
        {"record_id": "cnki-1"},
        ttl_minutes=30,
    )
    with pytest.raises(InvalidPlan, match="does not match"):
        ledger.confirm_plan(plan_id, "wrong", PlanKind.PDF_DOWNLOAD)
    confirmed = ledger.confirm_plan(plan_id, token, PlanKind.PDF_DOWNLOAD)
    assert confirmed["payload"]["record_id"] == "cnki-1"
    with pytest.raises(InvalidPlan, match="already committed"):
        ledger.confirm_plan(plan_id, token, PlanKind.PDF_DOWNLOAD)


def test_plan_consumption_and_recovery_row_are_one_transaction(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    plan_id, token, _ = ledger.create_plan(
        PlanKind.ZOTERO_IMPORT,
        {"items": [{"record_id": "cnki-1"}]},
        ttl_minutes=30,
    )
    confirmed = ledger.confirm_plan(
        plan_id,
        token,
        PlanKind.ZOTERO_IMPORT,
        operation_specs=[
            {
                "record_id": "cnki-1",
                "mode": "metadata_only",
                "payload": {"record_id": "cnki-1"},
            }
        ],
    )
    assert len(confirmed["operation_ids"]) == 1
    operations = ledger.list_operations(plan_id)
    assert operations[0]["id"] == confirmed["operation_ids"][0]


def test_expired_plan_state_is_persisted(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    plan_id, token, _ = ledger.create_plan(
        PlanKind.PDF_DOWNLOAD,
        {"record_id": "cnki-1"},
        ttl_minutes=0,
    )
    with pytest.raises(InvalidPlan, match="expired"):
        ledger.confirm_plan(plan_id, token, PlanKind.PDF_DOWNLOAD)
    assert ledger.get_plan(plan_id)["state"] == PlanState.EXPIRED.value
