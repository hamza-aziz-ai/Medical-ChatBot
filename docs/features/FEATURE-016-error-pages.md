# FEATURE-016: The site's own 404 and maintenance pages

**Goal.** Visitors see Mr. Healthcare's own pages, not Cloudflare's or the app at a wrong address: a 404 page for unknown paths and a maintenance page while an update closes the site (D-035).

**Scope.** `frontend/public/404.html` and `error.css`, `docker/nginx.conf` (real 404s), `hosting/cloudflare/maintenance.js` and its test `frontend/tests/maintenance.test.mjs`, the 404 check in `scripts/compose_smoke.sh`, and the Worker's setup in `hosting/oracle/README.md`.

**Design.** See D-035.

**Status.** Built. The 404 page ships with the next release. The maintenance page needs the owner's one-time Worker setup in Cloudflare.

**Open questions.** Whether a Worker's request to its own zone gets status 530 while the tunnel is closed (A-25), seen at the first update after the Worker is installed.

## Log

- 2026-10-29: Built. nginx with the new configuration: `/`, `/index.html` and assets 200; `/no-such-page`, `/404.html`, `/assets/` and a missing asset 404 with the page; the security headers unchanged. Worker tests: origin answers (200, 404, 503) pass through; 502, 504, 522, 530 and a failed fetch give the maintenance page with 503 and `no-store`.
