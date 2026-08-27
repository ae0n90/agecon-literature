---
name: agecon-literature-research
description: Use with AgEcon Literature MCP for Chinese academic literature discovery, CNKI metadata and abstract retrieval, selective PDF acquisition, Zotero 10 Local API import planning, and evidence-aware mapping of themes, authors, development, methods, data, and findings. Trigger for literature searches, 选题探索, 文献综述, 研究史梳理, 重要作者识别, CNKI 检索, or importing selected sources into Zotero.
---

# AgEcon Literature Research

Use the AgEcon MCP as the deterministic retrieval and persistence layer. Use this
Skill for search strategy, selection, verification, synthesis, and decisions
about when full text is actually needed.

## Hard boundaries

- Never invent a paper, DOI, author, outlet, method, dataset, finding, reference,
  or citation relation.
- Treat the current result set as a bounded sample, never as the whole field.
- Keep source facts separate from synthesis. Cite MCP `record_id` values in
  working notes so every claim can be traced.
- Use the evidence labels in `references/evidence-levels.md`.
- Do not call Zotero commit or resume tools until the user has reviewed the exact
  plan and explicitly authorized that mutation. Zotero changes may sync online.
- Do not call `pdf_download` until the user has reviewed the selected title,
  download reason, destination, and plan. Download only PDF.
- Never reuse a confirmation token or apply it to a different plan.
- Do not auto-resolve fuzzy Zotero matches. Ask the user to choose or revise the
  plan.
- Never promise universal or permanent CNKI download access. Use only the
  user's current campus-IP, CARSI, or official VPN entitlement. Never request or
  store institutional passwords, copy session cookies, relay downloads, or
  bypass access controls.

## Choose a search mode

Read `references/search-modes.md`, then name the mode in the working note:

- Discovery: concept expansion and field mapping.
- Targeted: locate known papers, authors, outlets, or DOI.
- Lineage: bounded citation candidates and research-history tracing.
- Library: Zotero matching, selective import, and verification.

Combine modes sequentially when needed; do not run a large undirected search.

## Workflow

### 1. Frame the question before searching

Write a compact concept matrix:

- focal phenomenon and economic decision;
- Chinese synonyms, older terminology, and English equivalents;
- actors and institutional setting;
- mechanisms and competing explanations;
- outcomes;
- likely methods and data sources;
- scope exclusions.

For agricultural economics, also read `references/agricultural-economics.md`.

### 2. Create reproducible search sessions

If the user is off campus, access fails, or the active entitlement is uncertain,
first read `references/cnki-access.md` and follow its profile and fallback rules.

Use `lit_search` for several small, named query lanes rather than one oversized
query. Start with 10–20 results per lane. Prefer structured fields (`topic`,
`title`, `author`, `institution`, `keyword`, `abstract`, `journal`, `doi`) and use
`onebox` only for broad discovery.

Record why each lane exists. Vary one dimension at a time: core concept,
mechanism, outcome, method/data, author/institution, or historical terminology.

### 3. Triage before fetching abstracts

From search-result metadata, classify candidates as:

- core: directly addresses the question;
- bridge: links two literatures or time periods;
- methods/data anchor;
- context only;
- exclude, with a short reason.

Use `lit_get_records` with `hydrate=true` only for selected core/bridge/anchor
records. A title alone does not establish method, data, or findings.

### 4. Verify identity and evidence

For every paper used substantively, verify authors, title, year, outlet, DOI or
CNKI URL, and version when available. Mark unresolved differences `待核验`.

Use `zotero_match` before proposing any import. Report exact matches separately
from fuzzy candidates.

### 5. Expand the network cautiously

Use `lit_expand_relations` only with depth 1. In v0.1, `citations` can return RF
field candidates if enabled; `references` and `similar` may be unavailable.
Preserve the returned completeness flag. Never describe `candidate` as a verified
or exhaustive citation edge.

When relation data are incomplete, expand through new concept, author, title, or
journal searches and explain that this is query-driven snowballing.

### 6. Decide whether full text is necessary

Full text is justified when an abstract cannot resolve at least one of:

- identification strategy or estimating equation;
- exact dataset, unit, period, or sample construction;
- variable measurement;
- main coefficient/heterogeneity result;
- mechanism evidence;
- a contradiction relevant to the review;
- reference-list tracing.

For selected records, call `pdf_plan`. Present title, selection reason,
destination, and intended use. Pause for explicit approval. Only then call
`pdf_download` with that plan's token. If PDF validation fails, report the reason;
do not accept HTML, CAJ, or a renamed file.

### 7. Import to Zotero with reviewable intent

Choose one explicit mode:

- `metadata_only`: create source metadata only; exact existing records are
  skipped.
- `metadata_with_pdf`: create a new metadata parent and attach one validated PDF;
  any existing match is a conflict.
- `attach_pdf_to_existing`: attach a validated PDF to exactly one exact existing
  parent; never modify its metadata.

Call `zotero_plan_import`. Show the user each create/attach/skip/conflict action,
the target collection, the `item_type_basis`, and that Zotero may sync it. A
known thesis, conference paper, or newspaper record is an unsupported-type
conflict in v0.1; never force it into `journalArticle`. Pause for explicit approval.
Only then call `zotero_commit_import` with the matching token.

Afterward, call `zotero_verify_import`. For `recoverable_failed`, inspect the
ledger result, call `zotero_plan_resume`, show the exact continuation, pause for
approval, and only then call `zotero_resume_import`.

### 8. Build the initial literature map

Use `lit_find_authors` and `lit_session_summary` as descriptive inputs, then write:

1. scope and exact search coverage;
2. research themes and how they connect;
3. important authors, separating result frequency, known citation signal, and
   substantive role;
4. development timeline and turning points;
5. main methods and identification limits;
6. datasets, units, periods, and geographic coverage;
7. main findings, disagreements, and boundary conditions;
8. gaps and next searches;
9. `待核验` list.

Attach an evidence label and record IDs to every methods/data/findings statement.
Say “the abstract reports” for abstract-level claims. Reserve strong causal
language for designs and results verified at sufficient depth.

### 9. Export only when useful

Use `lit_export_session` for a reusable JSON evidence bundle or Markdown
scaffold. The exported analysis fields are intentionally blank; fill them with
this Skill's evidence-aware synthesis, not untraceable model memory.

## Tool contract

The Skill expects exactly these MCP tools:

<!-- tool-contract:start -->
`lit_search`, `lit_get_records`, `lit_find_authors`, `lit_session_summary`,
`lit_expand_relations`, `zotero_match`, `pdf_plan`, `pdf_download`,
`zotero_plan_import`, `zotero_commit_import`, `zotero_plan_resume`,
`zotero_resume_import`, `zotero_verify_import`, `lit_export_session`
<!-- tool-contract:end -->

If a required tool is absent, stop the affected branch and report an MCP/Skill
version mismatch. Do not improvise a Zotero write through another endpoint.
