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
6. **Full text** only when the abstract cannot settle identification, data,
   measurement, main results, mechanism evidence, a relevant contradiction or
   reference tracing. Call `pdf_plan`, present title, reason and destination,
   wait for approval, then `pdf_download`. A validation failure is a failure;
   never accept HTML, CAJ or a renamed file as a PDF.
7. **Import.** Choose `metadata_only`, `metadata_with_pdf` (new parent plus PDF)
   or `attach_pdf_to_existing` (one exact existing parent; metadata untouched).
   Import into the collection the MCP config allowlists; the recommended setup
   is a single Inbox collection the user files from by hand, so do not pick
   topic collections for the user. Call `zotero_plan_import`, show each
   create/attach/skip/conflict action, the target and `item_type_basis`, and
   note that Zotero may sync. Theses, conference papers and newspapers are
   unsupported-type conflicts in v0.1; do not force them into
   `journalArticle`. After approval, `zotero_commit_import`, then
   `zotero_verify_import`. For `recoverable_failed`, use `zotero_plan_resume`,
   show the continuation, and resume only after approval.
8. **After import,** do not edit Zotero metadata. List missing or doubtful
   fields (volume, issue, pages, DOI, session-only CNKI URL) for the user's own
   metadata tool, such as the Jasminum plugin. Keep provenance (record ID,
   evidence level, PDF hash) in the report and MCP ledger, not in Zotero fields
   that plugins may rewrite.
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
