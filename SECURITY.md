# Security policy

## Supported versions

Only the latest tagged release is supported during the alpha period.

## Local security model

- Bind network transports to loopback only.
- Never forward Zotero's port `23119` or expose it through a tunnel.
- Store remembered Zotero Local API keys in the operating-system keychain.
- Store CNKI profiles in the upstream package's user data directory, outside
  this repository.
- Keep the SQLite operation ledger and downloaded PDFs in the platform user data
  directory.
- Reject plans if Zotero's current `Zotero-Server-ID` differs from the server ID
  recorded when the plan was created.
- Treat all external metadata as untrusted text; never execute it or interpolate
  it into shell commands.

## Reporting

Open a private security advisory on the GitHub repository. Do not include API
keys, cookies, institutional credentials, downloaded papers, or personal library
contents in a public issue.
