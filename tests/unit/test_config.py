from pathlib import Path

import pytest
from pydantic import ValidationError

from agecon_literature_mcp.config import Settings, ZoteroSettings
from agecon_literature_mcp.exceptions import ConfigurationError


def test_runtime_paths_stay_under_selected_data_dir(tmp_path: Path) -> None:
    settings = Settings(runtime={"data_dir": tmp_path})
    settings.ensure_runtime_dirs()
    assert settings.database_path.parent == tmp_path
    assert settings.downloads_dir.is_dir()
    assert settings.exports_dir.is_dir()


def test_zotero_rejects_non_loopback_or_group_library() -> None:
    with pytest.raises(ValidationError):
        ZoteroSettings(base_url="https://api.zotero.org", library_path="/users/0")
    with pytest.raises(ValidationError):
        ZoteroSettings(library_path="/groups/123")


def test_runtime_data_is_rejected_inside_git_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    settings = Settings(runtime={"data_dir": tmp_path / "runtime"})
    with pytest.raises(ConfigurationError, match="must not be inside"):
        settings.ensure_runtime_dirs()
