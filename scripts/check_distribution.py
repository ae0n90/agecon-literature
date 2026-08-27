#!/usr/bin/env python3
"""Audit built artifacts for required files and forbidden local data."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def forbidden(names: list[str]) -> list[str]:
    markers = (
        ".DS_Store",
        "__pycache__",
        "cookies.json",
        "storage_state.json",
        ".sqlite",
        ".sqlite3",
        ".pdf",
        ".caj",
    )
    return [name for name in names if any(marker in name for marker in markers)]


def main() -> int:
    wheels = sorted(Path("dist").glob("*.whl"))
    sdists = sorted(Path("dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one wheel and one source distribution")

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = archive.namelist()
    with tarfile.open(sdists[0], "r:gz") as archive:
        source_names = archive.getnames()

    bad = forbidden(wheel_names + source_names)
    if bad:
        raise SystemExit(f"distribution contains forbidden local artifacts: {bad}")
    if not any(name.endswith("dist-info/licenses/LICENSE") for name in wheel_names):
        raise SystemExit("wheel is missing GPL license text")
    if not any(
        name.endswith("dist-info/licenses/THIRD_PARTY_NOTICES.md")
        for name in wheel_names
    ):
        raise SystemExit("wheel is missing third-party notices")
    required_source_suffixes = (
        "skills/agecon-literature-research/SKILL.md",
        "contracts/tools.json",
        "docs/architecture.md",
        "tests/unit/test_zotero.py",
    )
    for suffix in required_source_suffixes:
        if not any(name.endswith(suffix) for name in source_names):
            raise SystemExit(f"source distribution is missing {suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
