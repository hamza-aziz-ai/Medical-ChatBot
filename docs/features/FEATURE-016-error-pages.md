# FEATURE-016: The site's own 404 and maintenance pages

**Goal.** Visitors see Mr. Healthcare's own pages, not Cloudflare's or the app at a wrong address: a 404 page for unknown paths and a maintenance page while an update closes the site (D-035).

**Scope.** `frontend/public/404.html` and `error.css`, `docker/nginx.conf` (real 404s), `hosting/cloudflare/maintenance.js` and its test `frontend/tests/maintenance.test.mjs`, the 404 check in `scripts/compose_smoke.sh`, and the Worker's setup in `hosting/oracle/README.md`.

**Design.** See D-035.

**Status.** Live since v1.1.22 (2026-10-29): the 404 page from the web image, the maintenance page from the Worker the owner installed in Cloudflare.

**Open questions.** None.

## Log

- 2026-10-29: Built. nginx with the new configuration: `/`, `/index.html` and assets 200; `/no-such-page`, `/404.html`, `/assets/` and a missing asset 404 with the page; the security headers unchanged. Worker tests: origin answers (200, 404, 503) pass through; 502, 504, 522, 530 and a failed fetch give the maintenance page with 503 and `no-store`.
- 2026-10-29: Live. The owner installed the Worker (logs, traces and `workers.dev` off; `/api/*` routed to no Worker, checked with a marked test question that did not reach its events). During the v1.1.22 update the public site answered 503 with the maintenance page from 15:39:35 to 15:40:09 IST, then served the new 404 page (A-25 verified). Setting it up, one test question was logged before the `/api/*` route existed; the guide now orders the steps so that cannot happen.
