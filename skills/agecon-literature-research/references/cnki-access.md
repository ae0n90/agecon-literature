# CNKI access: download-time only

Search, metadata, abstracts and field mapping do not require an IP or login check.
Starting a persistent browser for those tasks must not call `ensure_login`.

When the user requests a PDF:

1. Inspect CNKI's own current institutional/network recognition in the download
   browser. Prefer direct campus-IP access; do not equate the presence of a
   personal-login button with lack of institutional entitlement.
2. If recognition is unknown, try the selected paper's explicit PDF control.
   A returned, validated PDF proves access to that paper. IP geolocation, a
   successful search, or a visible PDF link alone does not prove entitlement.
3. If the route redirects to institutional authentication or explicitly denies
   download access, use CNKI organization/institution login and the user's school
   SSO account. Authentication is interactive; never collect credentials in chat
   or config. Reuse the same profile after authentication. Never force SSO for a
   working campus-IP route.
4. Timeouts, CAPTCHA, missing controls, and subscription exclusions are distinct
   failures. Do not classify all failures as off-campus access. Never bypass a
   challenge or repeatedly retry downloads.

Only PDF is accepted. Keep the server's original PDF filename and verify bytes;
HTML, CAJ and missing/unsafe original filenames fail closed. No entitlement
check or SSO flow should run until a PDF is requested.
