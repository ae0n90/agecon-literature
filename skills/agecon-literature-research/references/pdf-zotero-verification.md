# Original PDF to Jasminum: verification and recovery

The tested path is: download the original named PDF -> create one independent
stored attachment -> upload and register its bytes -> let Jasminum create its
parent -> read back and check duplicates. Do not create a metadata parent first.

## Recognize completion

- Keep the download artifact path and import operation ID. Call
  `zotero_verify_import` for that same operation, never import again to poll.
- `verified=true` on a standalone import confirms attachment bytes only.
  `checks.original_filename_preserved` separately compares the current filename
  with the downloaded name. Report any plugin rename; do not rename it back.
- `pending_plugin` is not an upload failure. Wait about 20 seconds and read back;
  allow up to two minutes of processing, excluding user interaction. If still
  pending, inspect the plugin state and report it rather than repeating imports.
- Jasminum's CNKI browser has its own session. A successful direct PDF download
  does not establish that this session has passed CNKI verification. If its window
  shows a CAPTCHA or “未找到 Cookie”, ask the user to complete verification and
  click “确认完成验证”; then resume read-only checks of the same operation. Do not
  turn this into school SSO, invoke metadata-fetch menus, or fill fields manually.
- `parent_created` is evidence of a parent, not complete or correct metadata.
  Read title, authors, date and the fields appropriate to the publication type;
  for a journal article, check journal, issue, pages and DOI when available.
  An absent volume is not automatically an error. Inspect the returned abstract
  when claiming it was retrieved. Compare identity with the selected record.
- Run `zotero_match` again and confirm the observed parent is the only matching
  item; inspect its children through the official Local API if checking attachment
  count. Report uncertain matches instead of merging or deleting them.

## Detect a stale MCP connection

An installed package or updated skill does not reload an existing server process.
The current tool schema must accept `standalone_pdf` as the default import mode.
Read-only verification of a known standalone operation should return
`runtime.workflow_revision=original-pdf-jasminum-v1`, `metadata_status`, the
observed parent and attachment filenames. The revision identifies this workflow
contract, not an exact source commit or proof of future updates.

If the schema lacks standalone mode, or verification uses the legacy parent-only
result, report the active connection as stale. Do not test a stale connection with
new downloads or writes. After source updates, run `python3 scripts/bootstrap.py` from the project root
to reinstall the non-editable package. Then reload/reconnect through a supported
client mechanism and repeat the read-only verification. Restarting a client alone
does not refresh a stale installed wheel.
A separately launched MCP client proves only that new process is current, not
that the original chat connection has reloaded.

A second server can collide with a persistent CNKI browser profile. Diagnose the
profile owner before restarting only the identified task-owned browser. Do not
kill unrelated browser sessions or delete login data. A failed download's token
is not reusable; prepare a fresh plan under the tool's confirmation contract.


## Read-only acceptance fields

`verified` still describes attachment bytes in standalone mode. Report separately:
- `metadata_status`: pending recognition or parent created.
- `metadata_assessment.identity_status`: matched, conflict, or incomplete against
  the selected source record; inspect `identity_conflicts` and `compared_fields`.
- `required_fields_complete` and `missing_fields`: presence checks only, not proof
  that every field is correct. Journal checks include source, issue and pages;
  thesis checks include university. A DOI is required only if the source has one.
- `checks.single_expected_pdf` and `pdf_attachment_count`: whether the observed
  parent has exactly the expected PDF. This is not a library-wide duplicate audit.

Missing author/year in title matching yields `title_metadata_incomplete`, not an
exact match; it follows existing candidate conflict handling, without a new gate.
Poll only pending recognition, with a bounded wait. Conflicts or missing fields
belong in the report, not in automatic repair or repeated imports. Source records
may themselves be incomplete; a conflict calls for checking the original source.
`runtime.verification_revision=identity-fields-v1` identifies the new readback.
Do not infer a live MCP reload merely from changed source files or passing tests.
