from agecon_literature_mcp.cnki import canonicalize_cnki
from agecon_literature_mcp.models import (
    EvidenceLevel,
    LiteratureRecord,
    normalize_doi,
    normalize_title,
    stable_id,
)


def test_normalization_is_conservative() -> None:
    assert normalize_doi("https://doi.org/10.1234/ABC.1.") == "10.1234/abc.1"
    assert normalize_title(" 农业 服务\uff1a效率\uff1f ") == "农业服务效率"


def test_stable_id_prefers_source_identity() -> None:
    first = stable_id("cnki", "ABC", "Title", ["A"], 2020)
    second = stable_id("cnki", "ABC", "Changed", ["B"], 2021)
    assert first == second


def test_record_fingerprint_changes_with_source_metadata() -> None:
    record = LiteratureRecord(
        id="cnki-1",
        title="农业服务与效率",
        authors=["张三"],
        year=2024,
        evidence_level=EvidenceLevel.METADATA,
    )
    updated = record.model_copy(update={"abstract": "新的摘要"})
    assert record.fingerprint != updated.fingerprint


def test_cnki_identity_uses_database_filename_not_volatile_url_token() -> None:
    record = canonicalize_cnki(
        {
            "title": "示例论文",
            "authors": ["张三"],
            "date": "2024",
            "url": (
                "https://kns.cnki.net/kcms2/article/abstract?"
                "dbcode=CJFD&filename=NYJJ202401001&v=volatile"
            ),
        }
    )
    assert record.source_id == "CJFD:NYJJ202401001"
    assert "volatile" not in record.id


def test_cnki_generic_abstract_path_is_not_a_source_identity() -> None:
    first = canonicalize_cnki(
        {
            "title": "农业社会化服务市场发育",
            "authors": ["张三"],
            "date": "2024",
            "url": "https://kns.cnki.net/kcms2/article/abstract?v=first",
        }
    )
    second = canonicalize_cnki(
        {
            "title": "农业机械化服务与粮食效率",
            "authors": ["李四"],
            "date": "2024",
            "url": "https://kns.cnki.net/kcms2/article/abstract?v=second",
        }
    )
    assert first.source_id is None
    assert second.source_id is None
    assert first.id != second.id


def test_cnki_fallback_identity_ignores_volatile_url_token() -> None:
    payload = {
        "title": "农业社会化服务市场发育",
        "authors": ["张三"],
        "date": "2024",
    }
    first = canonicalize_cnki(
        {**payload, "url": "https://kns.cnki.net/kcms2/article/abstract?v=first"}
    )
    second = canonicalize_cnki(
        {**payload, "url": "https://kns.cnki.net/kcms2/article/abstract?v=second"}
    )
    assert first.id == second.id


def test_cnki_identity_accepts_explicit_filename_fields() -> None:
    record = canonicalize_cnki(
        {
            "title": "示例论文",
            "filename": "NYJJ202401001",
            "dbcode": "cjfd",
        }
    )
    assert record.source_id == "CJFD:NYJJ202401001"
