# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

### Changed

- Renamed the MCP, CLI, Python namespace, companion Skill, runtime directory,
  and repository path to the unified `agecon-literature` naming scheme.
- Added bilingual Chinese/English trigger wording in the Skill description.

- Shortened the companion Skill: each rule stated once, import target taken
  from the MCP config.
- README: placeholder clone path, recommended Inbox-only import setup,
  optional Jasminum pairing, gateway approval note, and upgrade path.

### Added

- Skill no-result protocol: zero CNKI hits are reported as
  `[待核验：知网未检得]` with recorded attempts, not as nonexistence.
- Single allowlisted collection becomes the default import target when root
  imports are disabled; `doctor` reports `import_targets`.

- Initial local-first MCP architecture and companion literature-research Skill.
- CNKI session storage, Zotero Local API client, PDF validation, and operation
  ledger foundations.
- Documented dedicated campus-IP and institutional CARSI profiles, official VPN fallback,
  and explicit non-circumvention boundaries for off-campus use.

### Fixed

- Attachment verification compares md5 only, since Zotero plugins rename files.
- Search results no longer downgrade previously hydrated records.
- DOIs are stripped of BOM and zero-width characters.

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
