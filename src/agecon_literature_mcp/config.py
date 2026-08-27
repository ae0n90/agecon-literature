"""Configuration loading and platform-specific runtime paths."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .exceptions import ConfigurationError

APP_NAME = "agecon-literature"
APP_AUTHOR = "AgEcon"
CONFIG_ENV = "AGECON_LIT_CONFIG"


class RuntimeSettings(BaseModel):
    """Paths for non-versioned, user-specific application data."""

    model_config = ConfigDict(extra="forbid")

    data_dir: Path | None = None
    database_name: str = "operations.sqlite3"
    download_subdir: str = "downloads"
    export_subdir: str = "exports"

    @field_validator("data_dir", mode="before")
    @classmethod
    def empty_path_is_none(cls, value: object) -> object:
        """Interpret an empty example-config path as the platform default."""
        return None if value == "" else value

    @field_validator("database_name", "download_subdir", "export_subdir")
    @classmethod
    def path_component_only(cls, value: str) -> str:
        """Reject path traversal and nested paths in path components."""
        if not value or Path(value).name != value or value in {".", ".."}:
            raise ValueError("must be one non-empty path component")
        return value


class CnkiSettings(BaseModel):
    """CNKI browser and search limits."""

    model_config = ConfigDict(extra="forbid")

    profile: str = "default"
    max_results: int = Field(default=100, ge=1, le=500)
    max_metadata_hydration: int = Field(default=20, ge=1, le=50)
    headless: bool = False
    enable_candidate_citation_search: bool = False


class PdfSettings(BaseModel):
    """Full-text download and validation limits."""

    model_config = ConfigDict(extra="forbid")

    max_bytes: int = Field(default=100 * 1024 * 1024, ge=1024, le=4 * 1024**3)
    require_pdf_extension: bool = False
    keep_verified_downloads: bool = True


class ZoteroSettings(BaseModel):
    """Official Zotero desktop Local API configuration."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:23119/api"
    library_path: str = "/users/0"
    allow_root_library: bool = True
    allowed_collections: list[str] = Field(default_factory=list)
    app_name: str = "AgEcon Literature MCP"
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @model_validator(mode="after")
    def local_user_library_only(self) -> ZoteroSettings:
        """Enforce loopback and a user-library path for v0.1."""
        normalized = self.base_url.rstrip("/")
        if normalized not in {
            "http://127.0.0.1:23119/api",
            "http://localhost:23119/api",
        }:
            raise ValueError("base_url must be the Zotero loopback Local API")
        self.base_url = normalized
        if self.library_path != "/users/0":
            raise ValueError("v0.1 supports only the local user's /users/0 library")
        return self

    @field_validator("allowed_collections")
    @classmethod
    def validate_collection_keys(cls, values: list[str]) -> list[str]:
        """Accept only Zotero object-key-shaped collection identifiers."""
        allowed = set("23456789ABCDEFGHIJKLMNPQRSTUVWXYZ")
        for value in values:
            if len(value) != 8 or any(char not in allowed for char in value):
                raise ValueError(f"invalid Zotero collection key: {value!r}")
        return list(dict.fromkeys(values))


class SafetySettings(BaseModel):
    """Write-plan and unsupported-mutation guardrails."""

    model_config = ConfigDict(extra="forbid")

    plan_ttl_minutes: int = Field(default=30, ge=5, le=240)
    max_batch_import: int = Field(default=20, ge=1, le=50)
    allow_existing_item_updates: bool = False
    allow_delete: bool = False

    @model_validator(mode="after")
    def v01_mutations_are_disabled(self) -> SafetySettings:
        """Fail closed if an unsupported destructive feature is enabled."""
        if self.allow_existing_item_updates or self.allow_delete:
            raise ValueError("existing-item updates and deletion are disabled in v0.1")
        return self


class Settings(BaseModel):
    """Top-level application settings."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    cnki: CnkiSettings = Field(default_factory=CnkiSettings)
    pdf: PdfSettings = Field(default_factory=PdfSettings)
    zotero: ZoteroSettings = Field(default_factory=ZoteroSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)

    @property
    def data_dir(self) -> Path:
        """Return the resolved, non-repository runtime data directory."""
        return self.runtime.data_dir or user_data_path(APP_NAME, APP_AUTHOR)

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.runtime.database_name

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / self.runtime.download_subdir

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / self.runtime.export_subdir

    def ensure_runtime_dirs(self) -> None:
        """Create application-owned runtime directories with user-only mode."""
        resolved = self.data_dir.expanduser().resolve()
        for candidate in (resolved, *resolved.parents):
            if (candidate / ".git").exists():
                raise ConfigurationError(
                    f"runtime data_dir must not be inside a Git repository: {resolved}"
                )
        for path in (self.data_dir, self.downloads_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)


def default_config_path() -> Path:
    """Return the conventional per-user TOML path."""
    return user_config_path(APP_NAME, APP_AUTHOR) / "config.toml"


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"cannot read configuration {path}: {exc}") from exc


def load_settings(path: Path | None = None) -> Settings:
    """Load optional TOML configuration and validate all safety boundaries."""
    configured = path
    if configured is None and os.environ.get(CONFIG_ENV):
        configured = Path(os.environ[CONFIG_ENV]).expanduser()
    if configured is None:
        candidate = default_config_path()
        configured = candidate if candidate.exists() else None

    payload: dict[str, Any] = _read_toml(configured) if configured else {}
    try:
        settings = Settings.model_validate(payload)
    except ValueError as exc:
        source = str(configured) if configured else "built-in defaults"
        raise ConfigurationError(f"invalid settings from {source}: {exc}") from exc
    settings.ensure_runtime_dirs()
    return settings


__all__ = [
    "APP_AUTHOR",
    "APP_NAME",
    "CONFIG_ENV",
    "Settings",
    "default_config_path",
    "load_settings",
]
