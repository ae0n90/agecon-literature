# Architecture and trust boundaries

## Separation of responsibilities

The MCP is the deterministic execution layer. It searches, normalizes, stores,
hashes, deduplicates, plans, writes, verifies, and records failures. It does not
decide that an author is “important”, infer a method from a title, or turn a
candidate relation into a complete network.

The companion Skill is the judgment layer. It expands concepts, selects papers
for deeper inspection, labels evidence, compares themes and methods, and writes
the initial literature map. Its claims must point back to record IDs and evidence
levels supplied by the MCP.

## Data flow

```text
research question
  -> Skill concept matrix
  -> lit_search (one or more bounded sessions)
  -> local canonical records + original source payload
  -> lit_get_records for selected abstracts
  -> optional candidate relation expansion
  -> Zotero read-only matching
  -> optional pdf_plan -> explicit approval -> pdf_download -> PDF validation
  -> zotero_plan_import -> explicit approval -> zotero_commit_import
  -> zotero_verify_import
  -> Skill evidence-aware literature map
```

## Runtime storage

`platformdirs` selects the operating-system data directory. On macOS the default
is under `~/Library/Application Support/agecon-literature/`.

- `operations.sqlite3`: search sessions, canonical records, plans, import state.
- `downloads/`: verified PDF-only downloads.
- `exports/`: user-requested JSON or Markdown exports.

CNKI profile state is currently managed by the pinned upstream under
`~/.cnki-mcp/profiles/`. Zotero remembered write keys are partitioned by
`Zotero-Server-ID` and stored in the OS keychain.

## Mutation gate

Every PDF download and Zotero write follows:

```text
read and validate
  -> persist plan + snapshot fingerprints
  -> return exact actions + short-lived token
  -> user reviews and explicitly approves
  -> consume token atomically
  -> revalidate record/PDF/Zotero server identity
  -> execute and verify
```

Tokens are stored only as SHA-256 hashes in the ledger and cannot be reused.

## Zotero attachment state machine

```text
planned
  -> metadata_created        (new metadata modes only)
  -> attachment_created      (PDF modes only)
  -> bytes_uploaded
  -> upload_registered
  -> verified
  -> complete

any write/verification failure -> recoverable_failed
recoverable_failed -> new resume plan -> explicit approval -> safe continuation
```

Because network responses can be lost after Zotero commits a change, created
items carry a local operation marker. Resume first reconciles that marker before
creating anything again. The local ledger is authoritative for recovery; a
Zotero write token alone is not.

## Duplicate policy

1. DOI exact.
2. Stored CNKI source ID exact.
3. Normalized title + first author + year exact.
4. Title similarity candidate.
5. PDF MD5/SHA-256 where attachment metadata is available.

Levels 1–3 may justify a safe skip or an explicitly requested attachment to one
unambiguous parent. Level 4 always pauses for human resolution. No item is
automatically merged or overwritten.

## Failure posture

- Changed `Zotero-Server-ID`: invalidate the plan.
- Missing or one-use write key: stop and request interactive CLI authorization.
- Login HTML, CAJ, malformed or oversized bytes: reject as non-PDF.
- CNKI security verification: stop for the user to complete it.
- Ambiguous duplicate: return conflict and create no write plan.
- Incomplete relation source: report `candidate`, `partial`, or `unavailable`.
