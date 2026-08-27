"""AgEcon Literature MCP public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agecon-literature-mcp")
except PackageNotFoundError:  # pragma: no cover - source checkout fallback
    __version__ = "0.1.0"

__all__ = ["__version__"]
