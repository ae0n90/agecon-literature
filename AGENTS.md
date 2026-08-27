# Project Instructions: AgEcon Literature MCP

This repository contains a local-first literature workflow MCP and its companion
Codex skill. The MCP performs deterministic retrieval, persistence, validation,
and Zotero API operations. The skill performs query expansion, evidence-aware
synthesis, and academic judgment.

## Non-negotiable boundaries

- Use the Zotero 10 official Local API at `127.0.0.1:23119/api`; do not use
  Zotero Connector private endpoints or write directly to Zotero's SQLite file.
- Never place Zotero keys, CNKI cookies, browser profiles, search histories,
  downloaded PDFs, or the operation database in Git.
- Zotero writes and PDF downloads use a persisted `plan -> commit -> verify`
  workflow. A commit requires the exact short-lived confirmation token from the
  corresponding plan.
- Do not expose Zotero write-key authorization as an MCP tool. Authorization is
  an interactive CLI action and remembered keys go to the operating-system
  keychain.
- Do not delete Zotero items, overwrite existing metadata, auto-merge fuzzy
  duplicates, or import non-PDF full text in v0.1.
- Treat CNKI reference/citation/similarity coverage as partial unless the source
  explicitly proves completeness.
- Keep source metadata and model-authored analysis separate. Never turn an
  abstract-only inference into a full-text finding.
- Live CNKI and live Zotero write tests are opt-in and excluded from default CI.

## Engineering rules

- Keep the public MCP tool catalog in `src/agecon_literature_mcp/tool_catalog.py`.
  `contracts/tools.json` and Skill references must be checked against it.
- Add synthetic offline tests for all state transitions and HTTP writes.
- Preserve operation ledger rows after failure so an interrupted attachment
  upload can be inspected or safely resumed.
- Keep machine-specific paths, personal activity logs, and authorization events
  out of public files and source distributions.
- Pin upstream CNKI code to an immutable commit and update
  `THIRD_PARTY_NOTICES.md` when the pin changes.
- Run `python3 scripts/bootstrap.py`, then `uv run --no-sync ruff check .`,
  `uv run --no-sync mypy`, `uv run --no-sync pytest`, the contract checker, and
  `uv build` before a release.
- Runtime commands and MCP client examples must use `uv run --no-editable` on
  affected macOS environments. A bare `uv run` can restore an editable `.pth`
  install that Python skips when the virtual environment carries `UF_HIDDEN`.

## File management

- Application source: `src/agecon_literature_mcp/`
- Companion Skill: `skills/agecon-literature-research/`
- Architecture and protocols: `docs/`
- Synthetic fixtures only: `tests/fixtures_synthetic/`
- Public progress notes describe product changes only; keep personal operation
  logs outside the repository.
- Generated/runtime user data belongs under the platform data directory, never
  under this repository.
