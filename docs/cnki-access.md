# CNKI access profiles

## What this project can and cannot provide

AgEcon Literature MCP can reuse an authenticated CNKI browser profile from any
location. It cannot create, transfer, or extend institutional entitlement. A PDF
is available only when the current user and institution are authorized for that
content at the time of download.

The project does not copy cookies between users, store institutional passwords,
relay downloads through a cloud server, disguise traffic, bypass paywalls, or
automate bulk full-text acquisition.

## Recommended profiles

### Campus IP

Use `default` while connected to the authorized campus network:

```bash
uv run --no-editable agecon-literature cnki-init --profile default
```

IP recognition may stop working when the computer leaves campus. A browser
profile created only under campus IP is not evidence of off-campus entitlement.

### Institutional CARSI (preferred off campus)

Use your own institution's CARSI login and a dedicated browser profile.
Consult your library's instructions for subscribed resources and access routes.

1. Run:

   ```bash
   uv run --no-editable agecon-literature cnki-init --profile institution-carsi
   ```

2. In the CNKI institutional-login browser, choose your own institution.
3. Complete unified authentication yourself. Do not provide credentials to the
   MCP or store them in its configuration.
4. Select the profile in the external application configuration:

   ```toml
   [cnki]
   profile = "institution-carsi"
   ```

5. Restart the MCP client. Run a small metadata search first. Verify actual PDF
   entitlement only through the normal `pdf_plan` -> explicit approval ->
   `pdf_download` workflow for one selected paper.

### Institutional VPN (fallback)

If CARSI does not cover a database route, connect the computer to the official
institutional VPN outside this MCP, then initialize or refresh a normal CNKI profile. The
MCP does not install, configure, start, or share VPN access.

Consult your institution's official VPN instructions.

## Failure handling

- Search works but PDF fails: metadata availability is not full-text
  entitlement. Do not retry in a loop; review the source page and subscription.
- Login/session expired: rerun `cnki-init` for the configured profile and finish
  authentication interactively.
- Security verification appears: stop automation and let the user complete it.
- Returned bytes are HTML, CAJ, malformed, or oversized: validation rejects the
  file and does not treat it as a PDF.
- CARSI and VPN both fail: use the library's document-delivery route or import
  metadata only. Do not attempt technical circumvention.

## Verification boundary

Campus-IP metadata search and visible PDF controls can be tested on campus, but
off-campus CARSI/VPN behavior must be tested after actually leaving the campus
network. A current on-campus test cannot establish remote entitlement.
