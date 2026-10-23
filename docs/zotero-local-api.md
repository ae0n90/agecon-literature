# Zotero 10 Local API implementation notes

AgEcon Literature MCP uses only the official Local API rooted at
`http://127.0.0.1:23119/api`.

Authoritative protocol references:

- [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)
- [Zotero write requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [Zotero file uploads](https://www.zotero.org/support/dev/web_api/v3/file_upload)

## Identity and authorization

1. `GET /api/` reads `Zotero-API-Version`, `Zotero-Schema-Version`, and
   `Zotero-Server-ID`.
2. Plans pin `Zotero-Server-ID`; every commit probes again and aborts if it
   changed.
3. `POST /api/local/authorize` is available only through the interactive CLI,
   not as an MCP tool.
4. The user must choose `Always Allow` for multi-request PDF imports. Remembered
   keys are stored in the OS keychain and partitioned by server ID.
5. All write requests include `Zotero-Server-ID`, `Zotero-API-Key`, and API
   version 3. Creation requests also use a random `Zotero-Write-Token`.

## Full attachment upload

Default PDF imports create a standalone stored-file attachment, without a
`parentItem` or bibliographic metadata. Jasminum handles automatic recognition;
no plugin private API, AI metadata extraction, or UI automation is used. The
attachment title and filename are the original server filename.

For a stored-file attachment:

1. Create the standalone attachment item with `linkMode=imported_file`.
2. POST MD5, filename, byte size, and millisecond mtime to the attachment file
   endpoint with `If-None-Match: *`.
3. POST exact PDF bytes to the returned local upload URL.
4. Register the returned upload key at the file endpoint.
5. GET the attachment and compare MD5. Read its `parentItem` to observe plugin
   completion separately. Plugins may subsequently rename files; the MCP does not.

Each successful boundary is persisted before proceeding. This is intentionally
not presented as one atomic transaction.

## Recognition acceptance

The original-filename standalone workflow has been exercised end to end against
Zotero with Jasminum. After an interactive CNKI verification in the plugin's own
browser, the existing attachment acquired a bibliographic parent automatically;
no second import or metadata write was required. This is an observed integration
path, not a guarantee that every PDF can be recognized.

`zotero_verify_import` reports attachment integrity, original-filename preservation
and plugin parent creation separately. It includes the observed bibliographic
fields and `runtime.workflow_revision=original-pdf-jasminum-v1`. The revision
identifies the workflow contract so callers can detect a legacy running server;
it is not a source-build fingerprint. Missing optional bibliographic fields must
be judged against the publication, not filled by the MCP.

CNKI download access and the plugin's CNKI verification session are independent.
An outstanding plugin CAPTCHA calls for user interaction and read-only polling
of the same operation, not another download/import or automatic SSO. See the
companion Skill's `references/pdf-zotero-verification.md` for bounded checks.

## Deliberate omissions

- No Connector `/connector/*` endpoints.
- No direct access to Zotero's SQLite database.
- No Zotero Web API or cloud key fallback.
- No delete, update, merge, group-library write, or linked-file mode in v0.1.
