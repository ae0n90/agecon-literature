---
name: agecon-literature-research
description: "Find and verify Chinese academic literature with AgEcon Literature MCP: CNKI search, abstracts, authorized PDF/Zotero import plans and evidence-labelled literature maps. Use for 知网检索、查文献、核验参考文献能否检得、选题探索、文献综述、研究脉络与重要作者梳理, or importing selected CNKI records into Zotero. Citation-claim support checks belong to bibcheck."
---

# AgEcon Literature Research

The AgEcon MCP does retrieval, persistence, PDF validation and Zotero writes.
This Skill decides search strategy, selection, verification depth and synthesis.

## Boundaries

- Never invent a paper, DOI, author, finding or citation relation. Treat a
  result set as a bounded sample, never the whole field. Cite MCP
  `record_id` values in working notes and label claims with
  `references/evidence-levels.md`.
- PDF downloads and Zotero writes follow plan -> user approval -> commit with
  that plan's token. Show the plan and wait for explicit approval of it; never
  reuse a token or apply it to another plan.
- Do not auto-resolve fuzzy Zotero matches; let the user choose.
- Use only the user's own current CNKI entitlement; see
  `references/cnki-access.md` when access is off campus or uncertain.

## Choose a mode

- Targeted: a known title, DOI, author-year or outlet. Search the identifier
  directly and verify identity; skip concept matrices and field maps.
- Discovery: concept expansion and field mapping.
- Lineage: research history from verified anchor papers.
- Library: Zotero matching, selective import and verification.

`references/search-modes.md` has detailed strategy and the no-result protocol.

## Zero hits

Zero hits do not show that a work does not exist: a CNKI empty page, timeout,
verification page or expired session can all return `count: 0`. For a known
work, follow the no-result protocol before reporting, and report an unresolved
item as `[待核验：知网未检得]` with the attempts made.

## Workflow

1. **Frame** (Discovery/Lineage). When it helps choose queries, list the
   phenomenon, synonyms and older terms, actors, mechanisms, outcomes, methods
   and data, and exclusions. For agricultural-economics topics see
   `references/agricultural-economics.md`.
2. **Search.** Use `lit_search` in several small named lanes (10-20 results
   each), varying one dimension at a time. Prefer structured fields (`title`,
   `author`, `keyword`, `journal`, `doi`, ...); use `onebox` only for broad
   discovery.
3. **Triage** from metadata into core, bridge, methods/data anchor, context, or
   exclude. Hydrate only selected records with `lit_get_records(hydrate=true)`;
   a title alone does not establish method, data or findings.
4. **Verify** authors, title, year, outlet, DOI and version for every paper used
   substantively; mark differences `待核验`. Run `zotero_match` before any import
   and report exact matches separately from fuzzy candidates.
5. **Expand** with `lit_expand_relations` at depth 1 only. Relation results are
   candidates with a completeness flag, not verified or exhaustive citation
   edges; otherwise snowball through new title, author or journal searches.
6. **PDF download.** Only when the user requests PDF download, run the
   download workflow. Do not check IP entitlement or initiate login for searches,
   abstracts, or literature maps. `pdf_download` checks CNKI's current network
   recognition and tries direct campus-IP access first. Off campus, use the user's
   institutional/organization SSO login when direct access requires authentication;
   do not send an on-campus user through SSO by default. An unknown network signal
   or timeout is not proof that SSO is required. See `references/cnki-access.md`.
   Present `pdf_plan`, then consume its approved token. Preserve the server's
   original PDF filename exactly. Never derive a filename from the title, add a
   year/author prefix, or convert CAJ/HTML into a `.pdf` by renaming it. If the
   original name is missing or unsafe, report failure rather than inventing one.
7. **PDF import.** Use `zotero_plan_import(mode="standalone_pdf")` with the
   verified original-name PDF. The MCP creates only an independent stored PDF
   attachment in the allowlisted collection; it does not create a bibliographic
   parent or fill title/author/year/journal fields. Jasminum automatically detects
   the standalone Chinese PDF and creates its parent metadata in Zotero. Do not
   implement metadata recognition in the Skill, invoke AI extraction, detach and
   reattach files, merge parents, or drive plugin menus to imitate this process.
   Present the concrete plan and execute it once approved. Existing matching
   parents are conflicts, not permission to create duplicates or merge them.
   `metadata_with_pdf` is a compatibility alias for `standalone_pdf` in new plans.
   Only use `metadata_only` or `attach_pdf_to_existing` when explicitly requested;
   adding a child PDF does not trigger the standalone recognition workflow.
8. **Verify, without rewriting.** Call `zotero_verify_import` after commit. A
   verified attachment means the bytes arrived; `metadata_status=pending_plugin`
   means Jasminum has not yet created a parent. If the user needs the recognition
   result, read back after a bounded wait and report the actual status and fields.
   A created parent is not proof that all bibliographic fields are complete.
   Never synthesize missing fields or declare recognition successful merely
   because the upload completed. If the plugin is disabled, awaiting a candidate
   selection, or failed, report that state and leave recognition to Jasminum.
   Resume failed uploads using a fresh reviewed resume plan, without creating
   another attachment. Keep provenance in the MCP ledger. For the tested
   recognition sequence, CNKI verification prompts, duplicate checks and stale
   MCP detection, follow `references/pdf-zotero-verification.md`.

   When full-text reading is requested, reuse the local page cache and record
   actual reading coverage in existing notes, following
   `references/full-text-reading.md`. Extraction alone does not justify a `[全文]`
   claim. This adds no approval step.

9. **Map** (only when a field map or synthesis is requested). Use
   `lit_find_authors` and `lit_session_summary` as descriptive inputs and cover
   what is relevant: search coverage, themes, important authors (separating
   result frequency from substantive role), timeline, methods and
   identification limits, data, findings and disagreements, gaps and next
   searches, and a `待核验` list. Write "the abstract reports" for
   abstract-level claims.
10. **Export** with `lit_export_session` when a reusable JSON bundle or
    Markdown scaffold helps; fill its blank analysis fields from verified
    records, not memory.

## Tool contract

The Skill expects exactly these MCP tools:

<!-- tool-contract:start -->
`lit_search`, `lit_get_records`, `lit_find_authors`, `lit_session_summary`,
`lit_expand_relations`, `zotero_match`, `pdf_plan`, `pdf_download`,
`zotero_plan_import`, `zotero_commit_import`, `zotero_plan_resume`,
`zotero_resume_import`, `zotero_verify_import`, `lit_export_session`
<!-- tool-contract:end -->

Some clients load MCP tools lazily; search for a missing tool (for example with
`tool_search`) before reporting an MCP/Skill version mismatch. Never write to
Zotero through another endpoint.
