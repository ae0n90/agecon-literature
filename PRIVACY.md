# Privacy

AgEcon Literature MCP is local-first. Search sessions, query text, retrieved
metadata, download plans, PDFs, and Zotero operation records are stored on the
user's computer by default. They are not intentionally sent to a project-owned
server.

CNKI requests are sent to CNKI through the user's browser session. Zotero reads
and writes are sent only to the official Zotero desktop Local API on loopback.
Ordinary Zotero synchronization may later upload local changes to the user's
configured Zotero account; that behavior is controlled by Zotero, not this
project.

Do not commit runtime data. The repository ignore rules cover the standard
locations, but users remain responsible for reviewing `git status` before any
commit or push.
