# Search modes

## Discovery

Purpose: identify concepts, terminology, clusters, authors, and possible turning
points before the research question is fully fixed.

Sequence:

1. Core concept and synonyms.
2. Mechanism and competing explanation lanes.
3. Outcome lanes.
4. Data/method lanes.
5. Author/institution and older-terminology lanes.
6. Hydrate a small diverse set, then revise the concept matrix.

Stopping rule: new small lanes mostly repeat known authors/themes and no longer
change the provisional map. This indicates local saturation, not exhaustive
coverage.

## Targeted

Purpose: find a known work, author, journal, DOI, or citation identity.

Start with the narrowest verified field. Widen only after recording why the
narrow query failed. Compare versions and do not silently substitute a working
paper for a published article.

### No-result protocol

Use when a known title or cited reference returns zero hits. Record each
attempt (field, query, filters, count) and stop at the first hit whose identity
verifies.

1. Remove year, journal and source-type filters; the default search covers the
   whole CNKI database.
2. Search a normalized title (no subtitle, quotation marks or 书名号; try
   full-width and half-width punctuation), then two or three distinctive title
   terms with `title` and `topic`, then the cited author and year.
3. Repeat one query already known to hit. If it also returns zero, report CNKI
   unavailable or the session expired, not absence.
4. A similar title by the same authors is a candidate, not a match; report the
   differences. Otherwise label the item `[待核验：知网未检得]`, list the
   attempts, and in review feedback ask for journal, year, issue, pages or DOI
   rather than asserting the reference does not exist.

## Lineage

Purpose: trace how a question, mechanism, method, or dataset developed.

Start from verified anchor papers. Use depth-one relation candidates where
available, plus title/author/journal searches. For each edge, record whether it
is source-verified, candidate-only, or inferred from topical proximity.

## Library

Purpose: reconcile selected records with Zotero and preserve only useful items.

Always match first. Keep undecided candidates in search results; use metadata-only
imports only when explicitly requested. For approved PDF imports, preserve the
original filename and import a standalone attachment for Jasminum recognition.
Acquire PDFs only when the user requests full text.
Import into the allowlisted collection (recommended: one Inbox) and verify
every write by reading it back.
