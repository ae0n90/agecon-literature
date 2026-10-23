# Local full-text reading and evidence

Use this only when full-text reading is requested and a local PDF already exists.
Do not download or import again to populate a cache. From the agecon-literature
installation, run the local module with an explicit runtime/output cache directory
outside the source repository:

```sh
uv run --no-editable python -m agecon_literature_mcp.fulltext /path/original.pdf --cache-dir /path/output/fulltext-cache
```

The default output reports cache path, hit status, PDF page count and extraction
flags. Read a bounded range with `--start-page 2 --end-page 5`; omitting end reads
one page. Page numbers are PDF positions, not necessarily printed page numbers.
The canonical JSON stores numbered pages and provenance. Its key uses PDF SHA-256,
pypdf version, schema and options, so renaming does not cause re-extraction.
Corrupt or incompatible cache entries are regenerated atomically. Keep original
PDFs unchanged. Do not create parallel text/Markdown copies unless needed.

Extraction is not visual verification. Check relevant rendered pages for empty,
broken, mixed or unexpected text and for tables/equations before relying on them.
Hidden text can be wrong without an automatic flag. Escalate only affected pages
to OCR or another extractor when necessary; do not generalize a single paper's
font/color workaround. Record the alternative extractor and affected pages.

Add evidence to existing reading notes rather than requiring another report:
- Identity: record ID, PDF SHA-256/version, cache path and actual pages inspected.
- Each substantive claim: author finding, supporting page/passage, and separately
  the reader's synthesis. Mark unresolved discrepancies as pending verification.
- As applicable: research object, comparison group, measures, method and scope;
  competing explanations, contextual limits, shared datasets/cases across papers.

Use these fields proportionately: conceptual/case papers do not need an invented
causal design. Do not count overlapping cases as independent confirmations. For a
review, organize agreement and disagreement around questions and evidence, not
one abstract per paragraph. Never equate extraction coverage with reading coverage.
