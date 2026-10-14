# CNKI access decision rules

Use this reference when the user is off campus, a CNKI session fails, or PDF
entitlement is uncertain.

## Decision order

1. On campus: use the configured campus-IP profile.
2. Off campus: prefer the user's own institutional CARSI session in a dedicated
   profile (for example `institution-carsi`).
3. If CARSI does not cover the route: the user may connect the computer through
   the institution's official VPN outside the MCP, then refresh the profile.
4. If neither route grants access: continue with metadata/abstract work, use an
   authorized document-delivery option, or ask the user to supply the PDF.

CARSI and VPN extend only the institution's existing subscription. They do not
make every CNKI item downloadable.

## Safe operating rules

- Authentication is interactive. Never ask for, accept, store, or auto-fill the
  university password.
- Never copy cookies or browser profiles between people or machines.
- Never run a proxy/VPN relay or cloud download service for CNKI.
- A successful search does not prove PDF entitlement.
- Test PDF access only on a paper selected on substantive grounds, through the
  normal plan and approval workflow.
- HTML/login/CAJ responses and validation failures are failures, not PDFs.
- Security verification and reauthentication require the user.

Project setup details are in `docs/cnki-access.md` in the
AgEcon Literature MCP repository.
