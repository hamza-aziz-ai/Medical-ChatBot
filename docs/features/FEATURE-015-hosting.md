# FEATURE-015: Public hosting on an Oracle VM

**Goal.** Put Mr. Healthcare online for free, publicly and without login, with HTTPS and automatic updates (D-032).

**Scope.** `hosting/oracle/` (compose file, systemd units, setup guide), `scripts/update_stack.py` (hosted mode), `scripts/hosted_check.sh`, `docker/nginx.conf` (hosted-only include, API concurrency cap), `api/database.py` and `api/answer_searcher.py` (API driver limits), `docker/api.Dockerfile` (BUG-003), the About note, `release.yml` and `next_release.py` (the hosted compose as a release asset).

**Design.** See D-032.

**Status.** Built and tested locally; waiting for the owner to create the VM, the Aura instance and the tunnel, and for the first hosted release.

**Open questions.** Memory under a real update on the VM; whether Aura's pause is prevented by the health check; whether a Cloudflare rate-limit rule is needed.

## Log

- 2026-10-27: Built. Proxy trust proven by `scripts/hosted_check.sh`; hosted updater tests cover the order, preflight, recovery and crash cases; BUG-003 found and fixed; unreachable-graph time cut from 32.7 s to 11.0 s.
- 2026-10-27: The first release after merging (PR #62) failed in the hosted proxy check: in the release job, `compose create web` also created the api service, whose local image does not exist there. The release job now passes the release's API image, and the check creates only web; it passes with a missing API image.
