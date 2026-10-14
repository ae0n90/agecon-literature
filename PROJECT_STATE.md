# Project state

## Scope

AgEcon Literature MCP provides local-first CNKI discovery, metadata and abstract
retrieval, controlled PDF-only downloads, and Zotero 10 Local API imports.
The companion Skill supports evidence-aware literature discovery and synthesis.

## Implemented capabilities

- Persistent search sessions and canonical metadata records.
- On-demand detail and abstract hydration through a pinned CNKI adapter.
- Author, year, journal, and keyword summaries of retrieved records.
- PDF planning, validation, and a hash ledger.
- Read-only Zotero duplicate matching and planned imports through the Local API.
- Resumable attachment operations and read-back verification.
- Configurable import allowlists and a default target for a single collection.

## Known limits

- Reference and similarity graphs are not complete.
- Zero-hit searches do not distinguish all session and access failures.
- Volume, issue, pages, and document type may be missing from source metadata.
- Author searches may mix namesakes; combine author and title or journal terms.
- CNKI access depends on the user's current institutional entitlement.
- Approval behavior depends on the MCP client; see the README for gateway
  and client-policy considerations.
- No CAJ workflow, group-library writes, item deletion, metadata overwrite,
  or automatic duplicate merging is supported.

## Development

See the README for installation and offline validation commands. Live CNKI and
Zotero checks require a separately configured local environment and explicit
user authorization where applicable. Personal test sessions, local paths,
authorization events, and operation histories are not public project records.

Runtime diagnostics use `uv run --no-editable agecon-literature doctor` to avoid
editable-install startup issues in affected environments.
