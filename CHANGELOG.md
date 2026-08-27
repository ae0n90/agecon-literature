# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

### Changed

- Renamed the MCP, CLI, Python namespace, companion Skill, runtime directory,
  and repository path to the unified `agecon-literature` naming scheme.

### Added

- Initial local-first MCP architecture and companion literature-research Skill.
- CNKI session storage, Zotero Local API client, PDF validation, and operation
  ledger foundations.
- Documented dedicated campus-IP and institutional CARSI profiles, official VPN fallback,
  and explicit non-circumvention boundaries for off-campus use.

### Fixed

- Use non-editable runtime invocations so macOS `UF_HIDDEN` flags cannot make
  the project package disappear from Python's import path.
- Force Zotero's loopback Local API client to ignore environment proxies, so a
  stopped local server cannot be misreported as an upstream proxy HTTP 503.
- Force the bootstrap script to reinstall the non-editable project package
  after source changes instead of reusing a stale installed wheel.
- Run all blocking browser, SQLite, keyring, and Zotero Local API service calls
  outside the MCP asyncio event loop.
- Reject generic CNKI `abstract` paths as paper identifiers, fall back to stable
  bibliographic identity, and fail closed on distinct-record ID collisions.
