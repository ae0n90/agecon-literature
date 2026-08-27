"""Keep documented runtime commands independent of editable `.pth` files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_runtime_commands_are_non_editable() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uv run agecon-literature" not in readme
    assert '"run",\n  "--no-editable",\n  "agecon-literature"' in readme


def test_project_state_runtime_commands_are_non_editable() -> None:
    state = (ROOT / "PROJECT_STATE.md").read_text(encoding="utf-8")
    assert "uv run --no-sync agecon-literature" not in state
    assert "uv run --no-editable agecon-literature" in state
