# FEATURE-015: Public hosting on an Oracle VM

**Goal.** Put Mr. Healthcare online for free, publicly and without login, with HTTPS and automatic updates (D-032).

**Scope.** `hosting/oracle/` (compose file, systemd units, setup guide), `scripts/update_stack.py` (hosted mode), `scripts/hosted_check.sh`, `docker/nginx.conf` (hosted-only include, API concurrency cap), `api/database.py` and `api/answer_searcher.py` (API driver limits), `docker/api.Dockerfile` (BUG-003), the About note, `release.yml` and `next_release.py` (the hosted compose as a release asset).

**Design.** See D-032.

**Status.** Live at https://medical.hamzaaziz.dev since 2026-10-27, on v1.1.14, enrolled for automatic updates.

**Language model.** On since v1.1.18 (D-033 addendum), through the VM's own Ollama signed in to the owner's free plan; the direct API key needs paid credits.

**Open questions.** Memory under a real update on the VM; whether Aura's pause is prevented by the health check; whether a Cloudflare rate-limit rule is needed.

## Log

- 2026-10-27: Built. Proxy trust proven by `scripts/hosted_check.sh`; hosted updater tests cover the order, preflight, recovery and crash cases; BUG-003 found and fixed; unreachable-graph time cut from 32.7 s to 11.0 s.
- 2026-10-27: The first release after merging (PR #62) failed in the hosted proxy check: in the release job, `compose create web` also created the api service, whose local image does not exist there. The release job now passes the release's API image, and the check creates only web; it passes with a missing API image.
- 2026-10-27: v1.1.14's tag was refused (BUG-004); published with the owner's approval through a hand-pushed tag and a manual `release.yml` run from `main`.
- 2026-10-27: Deployed. Oracle micro VM (Mumbai, Ubuntu 24.04.5, 954 MiB, 2 GB swap, Docker Compose 5.6.1), AuraDB Free import of 658 diseases, update timer every 15 minutes. Public checks: HTTPS with a 301 from HTTP and HSTS; page, `/api/health` and an answer work; API responses `no-store` and `cf-cache-status: DYNAMIC`; 38 of 120 rapid requests from one address got 429; a sentinel question reached no container output or API log file.
