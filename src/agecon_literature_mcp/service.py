"""Deterministic application service used by the MCP and CLI."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .cnki import CnkiProvider
from .config import Settings
from .exceptions import ConflictDetected, InvalidPlan, SourceUnavailable, ZoteroError
from .models import (
    EvidenceLevel,
    ImportMode,
    LiteratureRecord,
    MatchKind,
    OperationState,
    PdfArtifact,
    PlanKind,
    RelationCompleteness,
    SearchSpec,
)
from .pdf import is_cnki_url, safe_filename, validate_pdf
from .storage import Ledger
from .zotero import ZoteroLocalClient


def public_record(record: LiteratureRecord, *, include_raw: bool = False) -> dict[str, Any]:
    """Return compact source metadata; raw DOM-derived payload is opt-in."""
    excluded = set() if include_raw else {"raw"}
    return record.model_dump(mode="json", exclude=excluded)


class LiteratureService:
    """Coordinate source adapters while preserving read/write boundaries."""

    def __init__(
        self,
        settings: Settings,
        *,
        ledger: Ledger | None = None,
        cnki: CnkiProvider | None = None,
        zotero: ZoteroLocalClient | None = None,
    ) -> None:
        self.settings = settings
        self.ledger = ledger or Ledger(settings.database_path)
        self.cnki = cnki or CnkiProvider(settings.cnki)
        self.zotero = zotero or ZoteroLocalClient(settings.zotero)

    def close(self) -> None:
        self.cnki.close()
        self.zotero.close()

    def doctor(self) -> dict[str, Any]:
        """Inspect local prerequisites without causing a write or CNKI request."""
        try:
            zotero = self.zotero.probe()
        except Exception as exc:
            zotero = {"available": False, "error": str(exc)}
        return {
            "runtime": {
                "data_dir": str(self.settings.data_dir),
                "database": str(self.settings.database_path),
                "downloads": str(self.settings.downloads_dir),
                "exports": str(self.settings.exports_dir),
            },
            "cnki": self.cnki.status(),
            "zotero": zotero,
            "import_targets": {
                "allow_root_library": self.settings.zotero.allow_root_library,
                "allowed_collections": list(self.settings.zotero.allowed_collections),
                "default_collection": self._default_collection(),
            },
            "safety": {
                "plan_ttl_minutes": self.settings.safety.plan_ttl_minutes,
                "max_batch_import": self.settings.safety.max_batch_import,
                "existing_item_updates": False,
                "delete": False,
            },
        }

    def _default_collection(self) -> str | None:
        """Use the only allowlisted collection when root imports are disabled (Inbox setup)."""
        zotero = self.settings.zotero
        if not zotero.allow_root_library and len(zotero.allowed_collections) == 1:
            return zotero.allowed_collections[0]
        return None

    def lit_search(
        self,
        query: str,
        *,
        field: str = "topic",
        year_from: int | None = None,
        year_to: int | None = None,
        journal: str | None = None,
        source_types: list[str] | None = None,
        sort_by: str = "relevance",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search CNKI and store an exact, replayable local session."""
        if year_from is not None and year_to is not None and year_to < year_from:
            raise ValueError("year_to must be greater than or equal to year_from")
        if sort_by not in {"relevance", "date", "citation", "comprehensive"}:
            raise ValueError("unsupported sort order")
        spec = SearchSpec(
            query=query,
            field=field,
            year_from=year_from,
            year_to=year_to,
            journal=journal,
            source_types=source_types or [],
            sort_by=sort_by,
            limit=min(limit, self.settings.cnki.max_results),
        )
        records = self._deduplicate_search_records(self.cnki.search(spec))
        session_id = self.ledger.create_session(spec)
        records = [self.ledger.upsert_record(record) for record in records]
        self.ledger.add_session_records(session_id, records)
        return {
            "session_id": session_id,
            "query": spec.model_dump(mode="json"),
            "count": len(records),
            "abstracts_hydrated": 0,
            "records": [
                {
                    "id": record.id,
                    "title": record.title,
                    "authors": record.authors,
                    "year": record.year,
                    "source_title": record.source_title,
                    "url": record.url,
                    "evidence_level": record.evidence_level.value,
                }
                for record in records
            ],
            "next": "Use lit_get_records with hydrate=true for selected IDs, not every hit.",
        }

    @staticmethod
    def _deduplicate_search_records(
        records: list[LiteratureRecord],
    ) -> list[LiteratureRecord]:
        """Reject canonical-ID collisions before a search result can overwrite records."""
        unique: dict[str, LiteratureRecord] = {}
        for record in records:
            previous = unique.get(record.id)
            if previous is None:
                unique[record.id] = record
                continue
            previous_identity = (
                previous.title_key,
                previous.first_author_key,
                previous.year,
            )
            current_identity = (
                record.title_key,
                record.first_author_key,
                record.year,
            )
            if previous_identity != current_identity:
                raise SourceUnavailable(
                    "CNKI returned distinct records with one canonical ID; "
                    "the search session was not stored"
                )
        return list(unique.values())

    def lit_get_records(
        self,
        *,
        session_id: str | None = None,
        record_ids: list[str] | None = None,
        hydrate: bool = False,
        include_raw: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Read stored records and optionally fetch selected detail pages/abstracts."""
        capped = min(limit, self.settings.cnki.max_metadata_hydration if hydrate else 100)
        records = self.ledger.get_records(
            session_id=session_id,
            record_ids=record_ids,
            limit=capped,
        )
        errors: list[dict[str, str]] = []
        hydrated: list[LiteratureRecord] = []
        for record in records:
            if hydrate and record.evidence_level in {
                EvidenceLevel.SEARCH_RESULT,
                EvidenceLevel.METADATA,
            }:
                try:
                    record = self.cnki.hydrate(record)
                    self.ledger.upsert_record(record)
                except Exception as exc:
                    errors.append({"record_id": record.id, "error": str(exc)})
            hydrated.append(record)
        return {
            "count": len(hydrated),
            "records": [public_record(record, include_raw=include_raw) for record in hydrated],
            "errors": errors,
        }

    def lit_find_authors(self, session_id: str, *, top_n: int = 20) -> dict[str, Any]:
        """Aggregate authors in one search session without inferring field influence."""
        records = self.ledger.get_records(session_id=session_id, limit=500)
        counts: Counter[str] = Counter()
        citations: Counter[str] = Counter()
        years: dict[str, list[int]] = {}
        ids: dict[str, list[str]] = {}
        for record in records:
            for author in record.authors:
                counts[author] += 1
                citations[author] += record.citation_count or 0
                ids.setdefault(author, []).append(record.id)
                if record.year is not None:
                    years.setdefault(author, []).append(record.year)
        ranked = sorted(counts, key=lambda name: (-counts[name], -citations[name], name))[:top_n]
        return {
            "session_id": session_id,
            "basis": "frequency within this search result; not a field-wide influence ranking",
            "authors": [
                {
                    "author": author,
                    "result_count": counts[author],
                    "known_citations_sum": citations[author],
                    "year_min": min(years.get(author, []), default=None),
                    "year_max": max(years.get(author, []), default=None),
                    "record_ids": ids[author],
                }
                for author in ranked
            ],
        }

    def lit_session_summary(self, session_id: str) -> dict[str, Any]:
        """Return descriptive coverage; methods/data/conclusions remain a Skill task."""
        session = self.ledger.get_session(session_id)
        records = self.ledger.get_records(session_id=session_id, limit=500)
        years = Counter(record.year for record in records if record.year is not None)
        sources = Counter(record.source_title for record in records if record.source_title)
        keywords = Counter(keyword for record in records for keyword in record.keywords)
        evidence = Counter(record.evidence_level.value for record in records)
        return {
            "session": session,
            "record_count": len(records),
            "year_distribution": dict(sorted(years.items())),
            "top_sources": sources.most_common(15),
            "top_keywords": keywords.most_common(30),
            "evidence_coverage": dict(evidence),
            "limits": [
                "Counts describe this query result, not the complete field.",
                "Methods, data, and conclusions require abstract/full-text "
                "evidence grading by the Skill.",
            ],
        }

    def lit_expand_relations(
        self,
        record_id: str,
        *,
        direction: str = "citations",
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Run only bounded, explicitly partial relation expansion."""
        if depth != 1:
            raise ValueError("v0.1 relation depth is fixed at 1")
        if direction not in {"citations", "references", "similar"}:
            raise ValueError("direction must be citations, references, or similar")
        if direction != "citations":
            return {
                "record_id": record_id,
                "direction": direction,
                "completeness": RelationCompleteness.UNAVAILABLE.value,
                "records": [],
                "reason": "v0.1 has no verified complete CNKI endpoint for this relation",
            }
        record = self.ledger.get_record(record_id)
        records = self.cnki.candidate_citations(record, limit=min(limit, 50))
        spec = SearchSpec(query=record.title, field="citation_candidate", limit=min(limit, 50))
        session_id = self.ledger.create_session(spec)
        for candidate in records:
            self.ledger.upsert_record(candidate)
        self.ledger.add_session_records(session_id, records)
        return {
            "record_id": record_id,
            "direction": direction,
            "session_id": session_id,
            "completeness": RelationCompleteness.CANDIDATE.value,
            "count": len(records),
            "records": [public_record(item) for item in records],
            "warning": "RF-field matches are candidates and may be incomplete or false-positive.",
        }

    def zotero_match(self, record_ids: list[str]) -> dict[str, Any]:
        """Read the local library and report candidates without changing it."""
        if len(record_ids) > self.settings.safety.max_batch_import:
            raise ValueError("record_ids exceeds the configured batch limit")
        server = self.zotero.probe()
        results = []
        for record_id in record_ids:
            record = self.ledger.get_record(record_id)
            matches = self.zotero.match(record)
            results.append(
                {
                    "record_id": record_id,
                    "matches": [match.model_dump(mode="json") for match in matches],
                }
            )
        return {"server_id": server["server_id"], "results": results}

    def pdf_plan(self, record_id: str) -> dict[str, Any]:
        """Plan one PDF-only browser download; no network mutation occurs here."""
        record = self.ledger.get_record(record_id)
        detail_url = record.url or record.source_id
        if not detail_url:
            raise InvalidPlan("record has no CNKI detail URL")
        if not is_cnki_url(detail_url):
            raise InvalidPlan("record detail URL is not an HTTPS cnki.net URL")
        destination = self.settings.downloads_dir / record.id / safe_filename(record.title)
        payload = {
            "record_id": record.id,
            "record_fingerprint": record.fingerprint,
            "detail_url": detail_url,
            "destination": str(destination),
            "format": "pdf",
        }
        plan_id, token, expires_at = self.ledger.create_plan(
            PlanKind.PDF_DOWNLOAD,
            payload,
            ttl_minutes=self.settings.safety.plan_ttl_minutes,
        )
        return {
            "plan_id": plan_id,
            "confirmation_token": token,
            "expires_at": expires_at.isoformat(),
            "record": {"id": record.id, "title": record.title},
            "destination": str(destination),
            "mutation": "downloads one PDF to local application storage",
        }

    def pdf_download(self, plan_id: str, confirmation_token: str) -> dict[str, Any]:
        """Consume a PDF plan, retrieve through the authenticated browser, and verify."""
        preview = self.ledger.get_plan(plan_id)
        if preview["kind"] != PlanKind.PDF_DOWNLOAD.value:
            raise InvalidPlan(f"plan {plan_id} is not a PDF download plan")
        preview_payload = preview["payload"]
        record = self.ledger.get_record(preview_payload["record_id"])
        if record.fingerprint != preview_payload["record_fingerprint"]:
            raise InvalidPlan("record metadata changed after download planning")
        plan = self.ledger.confirm_plan(
            plan_id,
            confirmation_token,
            PlanKind.PDF_DOWNLOAD,
            operation_specs=[
                {
                    "record_id": preview_payload["record_id"],
                    "mode": "pdf_download",
                    "payload": {"destination": preview_payload["destination"]},
                }
            ],
        )
        payload = plan["payload"]
        operation_id = plan["operation_ids"][0]
        try:
            record = self.ledger.get_record(payload["record_id"])
            if record.fingerprint != payload["record_fingerprint"]:
                raise InvalidPlan("record metadata changed after download planning")
            artifact = self.cnki.download_pdf(
                payload["detail_url"],
                Path(payload["destination"]),
                max_bytes=self.settings.pdf.max_bytes,
            )
            result = self.ledger.update_operation(
                operation_id,
                OperationState.COMPLETE,
                payload_updates={"artifact": artifact.model_dump(mode="json")},
            )
            return {"operation_id": operation_id, "artifact": result["payload"]["artifact"]}
        except Exception as exc:
            self.ledger.update_operation(
                operation_id,
                OperationState.RECOVERABLE_FAILED,
                payload_updates={"last_successful_state": OperationState.PLANNED.value},
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise

    @staticmethod
    def _exact_matches(matches: list[Any]) -> list[Any]:
        return [match for match in matches if match.kind != MatchKind.TITLE_CANDIDATE]

    @staticmethod
    def _journal_item_type_basis(record: LiteratureRecord) -> tuple[bool, str]:
        """Reject CNKI document classes known not to be journal articles."""
        source_key = (record.source_id or "").upper()
        database = source_key.split(":", 1)[0] if ":" in source_key else ""
        if database in {"CMFD", "CDFD", "CDMD"}:
            return False, f"CNKI database {database} identifies a thesis/dissertation"
        if database in {"CPFD", "IPFD"}:
            return False, f"CNKI database {database} identifies a conference paper"
        if database == "CCND":
            return False, "CNKI database CCND identifies a newspaper article"
        if database in {"CJFD", "CJFQ", "CAPJ"}:
            return True, f"CNKI database {database} identifies a journal record"
        return True, "document class unavailable; journalArticle is an explicit v0.1 assumption"

    def zotero_plan_import(
        self,
        record_ids: list[str],
        *,
        mode: str = ImportMode.METADATA_ONLY.value,
        collection_key: str | None = None,
        pdf_paths: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Read, validate, and deduplicate a proposed Zotero import without writing."""
        import_mode = ImportMode(mode)
        if not record_ids:
            raise ValueError("at least one record_id is required")
        if len(record_ids) > self.settings.safety.max_batch_import:
            raise ValueError("record_ids exceeds the configured batch limit")
        server = self.zotero.probe()
        collection_key = collection_key or self._default_collection()
        self.zotero.validate_collection(collection_key)
        paths = pdf_paths or {}
        planned_items: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for record_id in record_ids:
            record = self.ledger.get_record(record_id)
            journal_supported, item_type_basis = self._journal_item_type_basis(record)
            matches = self.zotero.match(record)
            exact = self._exact_matches(matches)
            fuzzy = [match for match in matches if match.kind == MatchKind.TITLE_CANDIDATE]
            item: dict[str, Any] = {
                "record_id": record.id,
                "record_fingerprint": record.fingerprint,
                "title": record.title,
                "evidence_level": record.evidence_level.value,
                "mode": import_mode.value,
                "collection_key": collection_key,
                "tags": list(dict.fromkeys(tags or ["agecon-literature", "CNKI"])),
                "zotero_item_type": "journalArticle",
                "item_type_basis": item_type_basis,
                "matches": [match.model_dump(mode="json") for match in matches],
            }
            if not journal_supported:
                conflicts.append(
                    {
                        "record_id": record.id,
                        "reason": (
                            f"{item_type_basis}; v0.1 structured import supports "
                            "journalArticle only"
                        ),
                    }
                )
                continue
            artifact: PdfArtifact | None = None
            if import_mode != ImportMode.METADATA_ONLY:
                path_value = paths.get(record.id)
                if not path_value:
                    conflicts.append(
                        {"record_id": record.id, "reason": "a validated PDF path is required"}
                    )
                    continue
                artifact = validate_pdf(Path(path_value), max_bytes=self.settings.pdf.max_bytes)
                item["artifact"] = artifact.model_dump(mode="json")

            if fuzzy:
                conflicts.append(
                    {
                        "record_id": record.id,
                        "reason": "fuzzy Zotero match requires human duplicate resolution",
                        "matches": item["matches"],
                    }
                )
                continue
            if import_mode == ImportMode.METADATA_ONLY:
                item["action"] = "skip_existing" if exact else "create_metadata"
                if exact:
                    item["existing_item_key"] = exact[0].item_key
            elif import_mode == ImportMode.METADATA_WITH_PDF:
                if exact:
                    conflicts.append(
                        {
                            "record_id": record.id,
                            "reason": (
                                "metadata item already exists; use "
                                "attach_pdf_to_existing explicitly"
                            ),
                            "matches": item["matches"],
                        }
                    )
                    continue
                item["action"] = "create_metadata_with_pdf"
            else:
                if len(exact) != 1:
                    conflicts.append(
                        {
                            "record_id": record.id,
                            "reason": "attach mode requires exactly one exact metadata match",
                            "matches": item["matches"],
                        }
                    )
                    continue
                if artifact is None:  # Defensive narrowing for static checking.
                    raise InvalidPlan("attach mode requires a validated PDF artifact")
                parent_key = exact[0].item_key
                same_hash = False
                for child in self.zotero.child_items(parent_key):
                    data = child.get("data", child)
                    if (
                        isinstance(data, dict)
                        and str(data.get("md5") or "").casefold() == artifact.md5
                    ):
                        same_hash = True
                        break
                item["action"] = "skip_pdf_existing" if same_hash else "attach_pdf"
                item["existing_item_key"] = parent_key
            planned_items.append(item)

        if conflicts:
            return {
                "status": "conflict",
                "committable": False,
                "conflicts": conflicts,
                "safe_items": planned_items,
                "instruction": "Resolve duplicates/PDF paths, then create a new plan.",
            }
        if all(item["action"] in {"skip_existing", "skip_pdf_existing"} for item in planned_items):
            return {
                "status": "noop",
                "committable": False,
                "items": planned_items,
                "instruction": "All requested records/files already exist; no write is needed.",
            }
        payload = {
            "mode": import_mode.value,
            "collection_key": collection_key,
            "items": planned_items,
        }
        plan_id, token, expires_at = self.ledger.create_plan(
            PlanKind.ZOTERO_IMPORT,
            payload,
            ttl_minutes=self.settings.safety.plan_ttl_minutes,
            server_id=str(server["server_id"]),
        )
        return {
            "status": "planned",
            "committable": True,
            "plan_id": plan_id,
            "confirmation_token": token,
            "expires_at": expires_at.isoformat(),
            "server_id": server["server_id"],
            "items": planned_items,
            "mutation": "creates Zotero items/attachments that may sync to zotero.org",
        }

    def _artifact_from_payload(self, payload: dict[str, Any]) -> PdfArtifact:
        artifact = PdfArtifact.model_validate(payload["artifact"])
        current = validate_pdf(artifact.path, max_bytes=self.settings.pdf.max_bytes)
        if current.sha256 != artifact.sha256:
            raise InvalidPlan("PDF bytes changed after planning")
        return current

    def _verify_parent(self, parent_key: str, record: LiteratureRecord) -> None:
        item = self.zotero.get_item(parent_key)
        data = item.get("data", item)
        title = data.get("title") if isinstance(data, dict) else None
        if title != record.title:
            raise ZoteroError("created Zotero metadata could not be verified by title")

    def _run_import_operation(self, operation_id: str, server_id: str) -> dict[str, Any]:
        operation = self.ledger.get_operation(operation_id)
        payload = operation["payload"]
        last_state = OperationState(
            payload.get("last_successful_state", operation["state"])
            if operation["state"] == OperationState.RECOVERABLE_FAILED.value
            else operation["state"]
        )
        record = self.ledger.get_record(operation["record_id"])
        if record.fingerprint != payload["record_fingerprint"]:
            raise InvalidPlan("record metadata changed after Zotero planning")
        action = payload["action"]
        if action in {"skip_existing", "skip_pdf_existing"}:
            return self.ledger.update_operation(operation_id, OperationState.COMPLETE)

        parent_key = payload.get("zotero_parent_key") or payload.get("existing_item_key")
        if action.startswith("create_") and not parent_key:
            marker_items = self.zotero.find_by_operation_marker(operation_id)
            if len(marker_items) == 1:
                parent_key = marker_items[0].get("key") or marker_items[0].get("data", {}).get(
                    "key"
                )
            else:
                current_matches = self._exact_matches(self.zotero.match(record))
                if current_matches:
                    raise ConflictDetected(
                        "an exact Zotero item appeared after planning; "
                        "no automatic merge was attempted"
                    )
                item_payload = self.zotero.item_payload(
                    record,
                    collection_key=payload.get("collection_key"),
                    tags=payload.get("tags") or [],
                )
                item_payload["extra"] += f"\nAgEcon-Operation: {operation_id}"
                parent_key = self.zotero.create_item(
                    item_payload,
                    expected_server_id=server_id,
                )
            self.ledger.update_operation(
                operation_id,
                OperationState.METADATA_CREATED,
                payload_updates={
                    "zotero_parent_key": parent_key,
                    "last_successful_state": OperationState.METADATA_CREATED.value,
                },
            )
            last_state = OperationState.METADATA_CREATED

        if not parent_key:
            raise InvalidPlan("operation has no verified Zotero parent item")
        self._verify_parent(str(parent_key), record)
        if action == "create_metadata":
            self.ledger.update_operation(
                operation_id,
                OperationState.VERIFIED,
                payload_updates={"last_successful_state": OperationState.VERIFIED.value},
            )
            return self.ledger.update_operation(operation_id, OperationState.COMPLETE)

        artifact = self._artifact_from_payload(payload)
        if action == "attach_pdf":
            for child in self.zotero.child_items(str(parent_key)):
                data = child.get("data", child)
                if isinstance(data, dict) and str(data.get("md5") or "").casefold() == artifact.md5:
                    return self.ledger.update_operation(
                        operation_id,
                        OperationState.COMPLETE,
                        payload_updates={"concurrent_pdf_skip": True},
                    )
        attachment_key = payload.get("zotero_attachment_key")
        if not attachment_key:
            marked_children = []
            for child in self.zotero.child_items(str(parent_key)):
                data = child.get("data", child)
                if isinstance(data, dict) and operation_id in str(data.get("note") or ""):
                    marked_children.append(child)
            if len(marked_children) == 1:
                child = marked_children[0]
                attachment_key = child.get("key") or child.get("data", {}).get("key")
            else:
                attachment_payload = self.zotero.attachment_payload(
                    parent_key=str(parent_key),
                    artifact=artifact,
                    title=f"{record.title} (PDF)",
                )
                attachment_payload["note"] = f"AgEcon-Operation: {operation_id}"
                attachment_key = self.zotero.create_item(
                    attachment_payload,
                    expected_server_id=server_id,
                )
            self.ledger.update_operation(
                operation_id,
                OperationState.ATTACHMENT_CREATED,
                payload_updates={
                    "zotero_attachment_key": attachment_key,
                    "last_successful_state": OperationState.ATTACHMENT_CREATED.value,
                },
            )
            last_state = OperationState.ATTACHMENT_CREATED

        if not attachment_key:
            raise ZoteroError("attachment creation did not return an item key")
        if last_state in {
            OperationState.PLANNED,
            OperationState.METADATA_CREATED,
            OperationState.ATTACHMENT_CREATED,
            OperationState.BYTES_UPLOADED,
        }:
            authorization = self.zotero.authorize_attachment_upload(
                str(attachment_key),
                artifact,
                expected_server_id=server_id,
            )
            if not authorization.get("exists"):
                self.zotero.upload_attachment_bytes(authorization, artifact)
                self.ledger.update_operation(
                    operation_id,
                    OperationState.BYTES_UPLOADED,
                    payload_updates={
                        "upload_key": authorization["upload_key"],
                        "last_successful_state": OperationState.BYTES_UPLOADED.value,
                    },
                )
                self.zotero.register_attachment_upload(
                    str(attachment_key),
                    str(authorization["upload_key"]),
                    expected_server_id=server_id,
                )
            self.ledger.update_operation(
                operation_id,
                OperationState.UPLOAD_REGISTERED,
                payload_updates={"last_successful_state": OperationState.UPLOAD_REGISTERED.value},
            )

        if not self.zotero.verify_attachment(str(attachment_key), artifact):
            raise ZoteroError("Zotero attachment metadata/hash verification failed")
        self.ledger.update_operation(
            operation_id,
            OperationState.VERIFIED,
            payload_updates={"last_successful_state": OperationState.VERIFIED.value},
        )
        return self.ledger.update_operation(operation_id, OperationState.COMPLETE)

    def zotero_commit_import(self, plan_id: str, confirmation_token: str) -> dict[str, Any]:
        """Consume a reviewed import plan and persist every non-atomic state."""
        preview = self.ledger.get_plan(plan_id)
        if preview["kind"] != PlanKind.ZOTERO_IMPORT.value:
            raise InvalidPlan(f"plan {plan_id} is not a Zotero import plan")
        operation_specs = [
            {
                "record_id": item["record_id"],
                "mode": item["mode"],
                "payload": item,
            }
            for item in preview["payload"]["items"]
        ]
        plan = self.ledger.confirm_plan(
            plan_id,
            confirmation_token,
            PlanKind.ZOTERO_IMPORT,
            operation_specs=operation_specs,
        )
        server_id = plan.get("server_id")
        if not server_id:
            raise InvalidPlan("Zotero import plan has no server identity")
        current = self.zotero.probe()
        if current["server_id"] != server_id:
            raise InvalidPlan("Zotero database changed after import planning")
        results = []
        for operation_id in plan["operation_ids"]:
            try:
                result = self._run_import_operation(operation_id, str(server_id))
            except Exception as exc:
                current_operation = self.ledger.get_operation(operation_id)
                last_state = current_operation["payload"].get(
                    "last_successful_state", current_operation["state"]
                )
                result = self.ledger.update_operation(
                    operation_id,
                    OperationState.RECOVERABLE_FAILED,
                    payload_updates={"last_successful_state": last_state},
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            results.append(result)
        return {
            "plan_id": plan_id,
            "operations": results,
            "complete": all(item["state"] == OperationState.COMPLETE.value for item in results),
        }

    def zotero_plan_resume(self, operation_id: str) -> dict[str, Any]:
        """Create a fresh short-lived plan for one failed import continuation."""
        operation = self.ledger.get_operation(operation_id)
        if operation["state"] != OperationState.RECOVERABLE_FAILED.value:
            raise InvalidPlan("only recoverable_failed operations can be resumed")
        original_plan = self.ledger.get_plan(operation["plan_id"])
        server = self.zotero.probe()
        if original_plan["server_id"] != server["server_id"]:
            raise InvalidPlan("Zotero database changed; failed operation cannot be resumed")
        payload = {"operation_id": operation_id}
        plan_id, token, expires_at = self.ledger.create_plan(
            PlanKind.ZOTERO_RESUME,
            payload,
            ttl_minutes=self.settings.safety.plan_ttl_minutes,
            server_id=str(server["server_id"]),
        )
        return {
            "plan_id": plan_id,
            "confirmation_token": token,
            "expires_at": expires_at.isoformat(),
            "operation": operation,
            "mutation": "continues the already approved Zotero import operation",
        }

    def zotero_resume_import(self, plan_id: str, confirmation_token: str) -> dict[str, Any]:
        """Consume a resume plan and continue from the persisted safe boundary."""
        plan = self.ledger.confirm_plan(plan_id, confirmation_token, PlanKind.ZOTERO_RESUME)
        operation_id = plan["payload"]["operation_id"]
        operation = self.ledger.get_operation(operation_id)
        if operation["state"] != OperationState.RECOVERABLE_FAILED.value:
            raise InvalidPlan("operation is no longer recoverable_failed")
        try:
            result = self._run_import_operation(operation_id, str(plan["server_id"]))
        except Exception as exc:
            current = self.ledger.get_operation(operation_id)
            result = self.ledger.update_operation(
                operation_id,
                OperationState.RECOVERABLE_FAILED,
                payload_updates={
                    "last_successful_state": current["payload"].get(
                        "last_successful_state", OperationState.PLANNED.value
                    )
                },
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        return result

    def zotero_verify_import(self, operation_id: str) -> dict[str, Any]:
        """Perform read-only verification of the persisted Zotero result."""
        operation = self.ledger.get_operation(operation_id)
        payload = operation["payload"]
        parent_key = payload.get("zotero_parent_key") or payload.get("existing_item_key")
        checks: dict[str, Any] = {"parent_exists": False, "attachment_verified": None}
        if parent_key:
            record = self.ledger.get_record(operation["record_id"])
            try:
                self._verify_parent(str(parent_key), record)
                checks["parent_exists"] = True
            except Exception as exc:
                checks["parent_error"] = str(exc)
        if payload.get("artifact") and payload.get("zotero_attachment_key"):
            artifact = self._artifact_from_payload(payload)
            checks["attachment_verified"] = self.zotero.verify_attachment(
                str(payload["zotero_attachment_key"]), artifact
            )
        return {
            "operation_id": operation_id,
            "ledger_state": operation["state"],
            "checks": checks,
            "verified": bool(checks["parent_exists"])
            and checks["attachment_verified"] is not False,
        }

    def lit_export_session(self, session_id: str, *, format: str = "json") -> dict[str, Any]:
        """Export source metadata and an empty evidence-aware synthesis scaffold."""
        if format not in {"json", "markdown"}:
            raise ValueError("format must be json or markdown")
        session = self.ledger.get_session(session_id)
        records = self.ledger.get_records(session_id=session_id, limit=500)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if format == "json":
            destination = self.settings.exports_dir / f"{session_id}-{timestamp}.json"
            payload = {
                "session": session,
                "records": [public_record(record, include_raw=True) for record in records],
                "analysis": {
                    "themes": [],
                    "important_authors": [],
                    "development_timeline": [],
                    "methods": [],
                    "data": [],
                    "findings": [],
                    "open_questions": [],
                    "note": (
                        "Analysis fields intentionally require Skill judgment and evidence labels."
                    ),
                },
            }
            destination.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            destination = self.settings.exports_dir / f"{session_id}-{timestamp}.md"
            lines = [
                f"# Literature session {session_id}",
                "",
                f"Query: `{session['spec']}`",
                "",
                "## Source records",
                "",
            ]
            for record in records:
                authors = ", ".join(record.authors) or "作者待核验"
                lines.append(
                    f"- [{record.evidence_level.value}] {record.title} — {authors} "
                    f"({record.year or '年份待核验'}) [{record.id}]"
                )
            lines.extend(
                [
                    "",
                    "## Evidence-aware synthesis (to be completed by the Skill)",
                    "",
                    "### Research themes",
                    "",
                    "### Important authors and why they matter",
                    "",
                    "### Development timeline",
                    "",
                    "### Methods and identification",
                    "",
                    "### Data",
                    "",
                    "### Main findings and disagreements",
                    "",
                    "### Gaps and items pending verification",
                    "",
                ]
            )
            destination.write_text("\n".join(lines), encoding="utf-8")
        return {"session_id": session_id, "format": format, "path": str(destination)}


__all__ = ["LiteratureService", "public_record"]
