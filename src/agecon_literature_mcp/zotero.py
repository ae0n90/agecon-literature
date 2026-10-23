"""Official Zotero 10 desktop Local API client and duplicate matcher."""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

import httpx
import keyring

from .config import ZoteroSettings
from .exceptions import (
    ZoteroAuthorizationRequired,
    ZoteroError,
    ZoteroServerChanged,
)
from .models import (
    LiteratureRecord,
    MatchKind,
    PdfArtifact,
    ZoteroMatch,
    normalize_doi,
    normalize_title,
)

KEYRING_SERVICE = "agecon-literature-mcp"


class KeyStore(Protocol):
    """Minimal key storage contract used by the Local API client."""

    def get(self, server_id: str) -> str | None: ...

    def set(self, server_id: str, key: str) -> None: ...

    def delete(self, server_id: str) -> None: ...


class SystemKeyStore:
    """Store remembered local API keys in the operating-system keychain."""

    @staticmethod
    def _account(server_id: str) -> str:
        return f"zotero-local:{server_id}"

    def get(self, server_id: str) -> str | None:
        return keyring.get_password(KEYRING_SERVICE, self._account(server_id))

    def set(self, server_id: str, key: str) -> None:
        keyring.set_password(KEYRING_SERVICE, self._account(server_id), key)

    def delete(self, server_id: str) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, self._account(server_id))
        except keyring.errors.PasswordDeleteError:
            return


def _creator_names(creators: Iterable[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for creator in creators:
        if creator.get("creatorType", "author") != "author":
            continue
        name = creator.get("name")
        if not name:
            name = " ".join(
                value for value in (creator.get("firstName"), creator.get("lastName")) if value
            )
        if name and str(name).strip():
            names.append(str(name).strip())
    return names


def _year_from_date(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    for token in value.replace("/", "-").split("-"):
        if len(token) == 4 and token.isdigit():
            year = int(token)
            if 1000 <= year <= 2200:
                return year
    return None


def assess_metadata(record: LiteratureRecord, data: dict[str, Any]) -> dict[str, Any]:
    """Read-only identity comparison and field-presence check, not metadata repair."""
    authors = _creator_names(data.get("creators") or [])
    pairs = {
        "title": (record.title_key, normalize_title(str(data.get("title") or ""))),
        "first_author": (record.first_author_key, normalize_title(authors[0]) if authors else ""),
        "year": (record.year, _year_from_date(data.get("date"))),
        "DOI": (normalize_doi(record.doi), normalize_doi(data.get("DOI") or None)),
    }
    compared = [key for key, (expected, actual) in pairs.items() if expected and actual]
    conflicts = [key for key in compared if pairs[key][0] != pairs[key][1]]
    strong = "DOI" in compared or all(k in compared for k in ("title", "first_author", "year"))
    required = ["itemType", "title", "date"]
    if data.get("itemType") == "journalArticle":
        required += ["publicationTitle", "issue", "pages"]
    elif data.get("itemType") == "thesis":
        required += ["university"]
    if record.doi:
        required.append("DOI")
    missing = [key for key in required if not str(data.get(key) or "").strip()]
    if not authors:
        missing.append("author")
    if data.get("date") and pairs["year"][1] is None:
        missing.append("parseable_year")
    return {
        "identity_status": "conflict" if conflicts else "matched" if strong else "incomplete",
        "identity_conflicts": conflicts,
        "compared_fields": compared,
        "missing_fields": missing,
        "required_fields_complete": not missing,
    }


class ZoteroLocalClient:
    """Small protocol-faithful client for Zotero 10's official Local API."""

    def __init__(
        self,
        settings: ZoteroSettings,
        *,
        key_store: KeyStore | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.key_store = key_store or SystemKeyStore()
        self.client = client or httpx.Client(
            follow_redirects=False,
            timeout=settings.request_timeout_seconds,
            # A loopback-only API must never inherit HTTP(S)/SOCKS proxies.
            # Otherwise a stopped Zotero can be misreported as a proxy's 503.
            trust_env=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _url(self, path: str) -> str:
        return f"{self.settings.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _check(response: httpx.Response, operation: str) -> httpx.Response:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = response.status_code
            if status == 401:
                raise ZoteroAuthorizationRequired(
                    "Zotero rejected the local write key; authorize again with "
                    "'agecon-literature zotero-authorize'"
                ) from exc
            if status == 412:
                raise ZoteroServerChanged(
                    f"Zotero rejected stale server/version state during {operation}"
                ) from exc
            raise ZoteroError(f"Zotero {operation} failed with HTTP {status}") from exc
        return response

    def probe(self) -> dict[str, Any]:
        """Read API and server identity without requesting write permission."""
        try:
            response = self.client.get(f"{self.settings.base_url}/")
        except httpx.HTTPError as exc:
            raise ZoteroError(
                "cannot reach Zotero Local API; start Zotero and enable local API access"
            ) from exc
        self._check(response, "probe")
        server_id = response.headers.get("Zotero-Server-ID")
        if not server_id:
            raise ZoteroError("Zotero response did not include Zotero-Server-ID")
        try:
            key_remembered = self.key_store.get(server_id) is not None
            key_store_error = None
        except Exception as exc:
            key_remembered = False
            key_store_error = type(exc).__name__
        result = {
            "available": True,
            "api_version": response.headers.get("Zotero-API-Version"),
            "schema_version": response.headers.get("Zotero-Schema-Version"),
            "server_id": server_id,
            "write_key_remembered": key_remembered,
        }
        if key_store_error:
            result["key_store_error"] = key_store_error
        return result

    def authorize_writes(self, *, require_remembered: bool = True) -> dict[str, Any]:
        """Prompt in Zotero and keep only a user-selected persistent key."""
        status = self.probe()
        server_id = str(status["server_id"])
        response = self.client.post(
            self._url("local/authorize"),
            json={"appName": self.settings.app_name},
            headers={"Zotero-Server-ID": server_id},
        )
        self._check(response, "write authorization")
        payload = response.json()
        key = payload.get("key")
        remembered = bool(payload.get("remember"))
        if not isinstance(key, str) or len(key) != 32:
            raise ZoteroError("Zotero returned an invalid local authorization payload")
        if require_remembered and not remembered:
            raise ZoteroAuthorizationRequired(
                "the one-use key was not stored; run authorization again and choose "
                "'Always Allow' because a PDF import requires multiple writes"
            )
        if remembered:
            self.key_store.set(server_id, key)
        return {
            "authorized": remembered or not require_remembered,
            "remembered": remembered,
            "server_id": server_id,
        }

    def _write_headers(
        self,
        *,
        expected_server_id: str,
        write_token: bool = False,
    ) -> dict[str, str]:
        current = self.probe()
        current_server_id = str(current["server_id"])
        if current_server_id != expected_server_id:
            raise ZoteroServerChanged(
                "Zotero database changed after the plan was created; create a new plan"
            )
        key = self.key_store.get(current_server_id)
        if not key:
            raise ZoteroAuthorizationRequired(
                "no remembered Zotero Local API key; run "
                "'agecon-literature zotero-authorize' and choose 'Always Allow'"
            )
        headers = {
            "Zotero-API-Key": key,
            "Zotero-API-Version": "3",
            "Zotero-Server-ID": current_server_id,
        }
        if write_token:
            headers["Zotero-Write-Token"] = secrets.token_hex(16)
        return headers

    def _read_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(self._url(path), params=params)
        self._check(response, "read")
        return response.json()

    def get_item(self, item_key: str) -> dict[str, Any]:
        payload = self._read_json(f"{self.settings.library_path}/items/{item_key}")
        if not isinstance(payload, dict):
            raise ZoteroError("Zotero returned a non-object item payload")
        return payload

    def search_items(
        self,
        query: str,
        *,
        limit: int = 50,
        qmode: str = "titleCreatorYear",
    ) -> list[dict[str, Any]]:
        payload = self._read_json(
            f"{self.settings.library_path}/items/top",
            params={
                "q": query,
                "qmode": qmode,
                "itemType": "-attachment",
                "limit": min(limit, 100),
                "format": "json",
            },
        )
        if not isinstance(payload, list):
            raise ZoteroError("Zotero returned a non-list search payload")
        return [item for item in payload if isinstance(item, dict)]

    def child_items(self, parent_key: str) -> list[dict[str, Any]]:
        """Read child attachments/notes for duplicate and recovery checks."""
        payload = self._read_json(
            f"{self.settings.library_path}/items/{parent_key}/children",
            params={"format": "json"},
        )
        if not isinstance(payload, list):
            raise ZoteroError("Zotero returned a non-list child-item payload")
        return [item for item in payload if isinstance(item, dict)]

    def find_by_operation_marker(self, operation_id: str) -> list[dict[str, Any]]:
        """Find items created by one operation without relying on write-token memory."""
        # Include attachments even after Jasminum has assigned a parent.
        payload = self._read_json(
            f"{self.settings.library_path}/items",
            params={"q": operation_id, "qmode": "everything", "limit": 100, "format": "json"},
        )
        if not isinstance(payload, list):
            raise ZoteroError("Zotero returned a non-list recovery payload")
        return [item for item in payload if isinstance(item, dict)]

    def match(self, record: LiteratureRecord, *, limit: int = 50) -> list[ZoteroMatch]:
        """Return exact and fuzzy candidates; never merge or modify them."""
        queries = [(record.title, "titleCreatorYear")]
        if record.source_id:
            queries.insert(0, (record.source_id, "everything"))
        if record.doi:
            queries.insert(0, (record.doi, "everything"))
        candidates: dict[str, dict[str, Any]] = {}
        for query, qmode in queries:
            for item in self.search_items(query, limit=limit, qmode=qmode):
                key = item.get("key") or item.get("data", {}).get("key")
                if key:
                    candidates[str(key)] = item

        matches: list[ZoteroMatch] = []
        for item_key, item in candidates.items():
            data = item.get("data", item)
            if not isinstance(data, dict):
                continue
            title = str(data.get("title") or "").strip()
            creators = _creator_names(data.get("creators") or [])
            year = _year_from_date(data.get("date"))
            doi = normalize_doi(data.get("DOI") if isinstance(data.get("DOI"), str) else None)
            extra = str(data.get("extra") or "")
            title_score = SequenceMatcher(None, record.title_key, normalize_title(title)).ratio()
            kind = MatchKind.NONE
            score = 0.0
            if record.doi and doi == record.doi:
                kind, score = MatchKind.DOI_EXACT, 1.0
            elif record.source_id and f"CNKI-ID: {record.source_id}" in extra:
                kind, score = MatchKind.SOURCE_KEY_EXACT, 1.0
            elif (
                record.title_key == normalize_title(title)
                and (
                    not record.first_author_key
                    or not creators
                    or record.first_author_key == normalize_title(creators[0])
                )
                and (record.year is None or year is None or record.year == year)
            ):
                if record.first_author_key and creators and record.year and year:
                    kind, score = MatchKind.TITLE_AUTHOR_YEAR_EXACT, 0.98
                else:
                    kind, score = MatchKind.TITLE_METADATA_INCOMPLETE, 0.9
            elif title_score >= 0.85:
                kind, score = MatchKind.TITLE_CANDIDATE, title_score
            if kind != MatchKind.NONE:
                matches.append(
                    ZoteroMatch(
                        item_key=item_key,
                        kind=kind,
                        title=title,
                        creators=creators,
                        year=year,
                        doi=doi,
                        score=score,
                    )
                )
        return sorted(matches, key=lambda match: (-match.score, match.item_key))

    def validate_collection(self, collection_key: str | None) -> None:
        """Apply configuration allowlist and verify the target exists."""
        if collection_key is None:
            if not self.settings.allow_root_library:
                raise ZoteroError(
                    "root-library imports are disabled; choose an allowlisted collection"
                )
            return
        if collection_key not in self.settings.allowed_collections:
            raise ZoteroError(f"collection {collection_key} is not allowlisted")
        payload = self._read_json(f"{self.settings.library_path}/collections/{collection_key}")
        if not isinstance(payload, dict):
            raise ZoteroError(f"collection {collection_key} could not be verified")

    @staticmethod
    def item_payload(
        record: LiteratureRecord,
        *,
        collection_key: str | None,
        tags: list[str],
    ) -> dict[str, Any]:
        """Map verified source metadata without inventing missing fields."""
        extra_lines = [f"Source: {record.source}"]
        if record.source_id:
            extra_lines.append(f"CNKI-ID: {record.source_id}")
        extra_lines.append(f"AgEcon-Evidence: {record.evidence_level.value}")
        return {
            "itemType": "journalArticle",
            "title": record.title,
            "creators": [{"creatorType": "author", "name": author} for author in record.authors],
            "abstractNote": record.abstract or "",
            "publicationTitle": record.source_title or "",
            "volume": record.volume or "",
            "issue": record.issue or "",
            "pages": record.pages or "",
            "date": str(record.year or ""),
            "DOI": record.doi or "",
            "url": record.url or "",
            "tags": [{"tag": tag} for tag in list(dict.fromkeys(tags))],
            "collections": [collection_key] if collection_key else [],
            "relations": {},
            "extra": "\n".join(extra_lines),
        }

    @staticmethod
    def attachment_payload(
        *,
        parent_key: str | None,
        artifact: PdfArtifact,
        title: str,
    ) -> dict[str, Any]:
        return {
            "itemType": "attachment",
            "linkMode": "imported_file",
            **({"parentItem": parent_key} if parent_key else {}),
            "title": title,
            "contentType": "application/pdf",
            "charset": "",
            "filename": artifact.path.name,
            "note": "",
            "tags": [],
            "relations": {},
        }

    def create_item(
        self,
        payload: dict[str, Any],
        *,
        expected_server_id: str,
    ) -> str:
        response = self.client.post(
            self._url(f"{self.settings.library_path}/items"),
            json=[payload],
            headers=self._write_headers(expected_server_id=expected_server_id, write_token=True),
        )
        self._check(response, "item creation")
        result = response.json()
        failed = result.get("failed") or {}
        if failed:
            raise ZoteroError("Zotero rejected the item payload")
        successful = result.get("successful") or result.get("success") or {}
        value = successful.get("0") or successful.get(0)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            key = value.get("key") or value.get("data", {}).get("key")
            if key:
                return str(key)
        raise ZoteroError("Zotero item response did not contain the created key")

    def upload_attachment_file(
        self,
        attachment_key: str,
        artifact: PdfArtifact,
        *,
        expected_server_id: str,
    ) -> dict[str, Any]:
        """Run all three documented phases as a convenience for CLI callers."""
        authorization = self.authorize_attachment_upload(
            attachment_key,
            artifact,
            expected_server_id=expected_server_id,
        )
        if authorization.get("exists") is True:
            return {"exists": True, "bytes_uploaded": False, "registered": True}
        self.upload_attachment_bytes(authorization, artifact)
        self.register_attachment_upload(
            attachment_key,
            str(authorization["upload_key"]),
            expected_server_id=expected_server_id,
        )
        return {"exists": False, "bytes_uploaded": True, "registered": True}

    def authorize_attachment_upload(
        self,
        attachment_key: str,
        artifact: PdfArtifact,
        *,
        expected_server_id: str,
    ) -> dict[str, Any]:
        """Phase 1: obtain a one-hour local upload authorization."""
        file_path = Path(artifact.path)
        endpoint = f"{self.settings.library_path}/items/{attachment_key}/file"
        headers = self._write_headers(expected_server_id=expected_server_id)
        headers["If-None-Match"] = "*"
        response = self.client.post(
            self._url(endpoint),
            data={
                "md5": artifact.md5,
                "filename": file_path.name,
                "filesize": str(artifact.size_bytes),
                "mtime": str(artifact.mtime_ms),
            },
            headers=headers,
        )
        self._check(response, "attachment upload authorization")
        authorization = response.json()
        if authorization.get("exists") == 1:
            return {"exists": True}
        upload_url = authorization.get("url")
        upload_key = authorization.get("uploadKey")
        content_type = authorization.get("contentType") or "application/octet-stream"
        if not isinstance(upload_url, str) or not isinstance(upload_key, str):
            raise ZoteroError("Zotero returned incomplete upload authorization")
        if upload_url.startswith("/"):
            upload_url = f"http://127.0.0.1:23119{upload_url}"
        return {
            "exists": False,
            "upload_url": upload_url,
            "upload_key": upload_key,
            "content_type": str(content_type),
        }

    def upload_attachment_bytes(
        self,
        authorization: dict[str, Any],
        artifact: PdfArtifact,
    ) -> None:
        """Phase 2: send exact PDF bytes using the upload-key URL."""
        upload_url = str(authorization["upload_url"])
        with Path(artifact.path).open("rb") as handle:
            response = self.client.post(
                upload_url,
                content=handle.read(),
                headers={"Content-Type": str(authorization["content_type"])},
            )
        self._check(response, "attachment byte upload")
        if response.status_code != 201:
            raise ZoteroError(
                f"Zotero attachment upload returned unexpected HTTP {response.status_code}"
            )

    def register_attachment_upload(
        self,
        attachment_key: str,
        upload_key: str,
        *,
        expected_server_id: str,
    ) -> None:
        """Phase 3: atomically move uploaded bytes into Zotero storage."""
        endpoint = f"{self.settings.library_path}/items/{attachment_key}/file"
        headers = self._write_headers(expected_server_id=expected_server_id)
        headers["If-None-Match"] = "*"
        response = self.client.post(
            self._url(endpoint),
            data={"upload": upload_key},
            headers=headers,
        )
        self._check(response, "attachment upload registration")
        if response.status_code != 204:
            raise ZoteroError(
                f"Zotero attachment registration returned unexpected HTTP {response.status_code}"
            )

    def verify_attachment(self, attachment_key: str, artifact: PdfArtifact) -> bool:
        item = self.get_item(attachment_key)
        data = item.get("data", item)
        if not isinstance(data, dict):
            return False
        # Compare content only: Zotero and its plugins may rename stored files.
        actual_md5 = str(data.get("md5") or "").casefold()
        return actual_md5 == artifact.md5.casefold()


__all__ = ["KEYRING_SERVICE", "KeyStore", "SystemKeyStore", "ZoteroLocalClient"]
