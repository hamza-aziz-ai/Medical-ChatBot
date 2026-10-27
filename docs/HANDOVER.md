# HANDOVER

Read this first, then [CONSTRAINTS.md](CONSTRAINTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Newest entry on top. Update it at the end of every session.

## Latest session: 2026-10-27 (model: Claude Opus 5.5, claude-opus-5-5; council with Codex/ChatGPT)

Done:
- The site is public at https://medical.hamzaaziz.dev (D-032, FEATURE-015): Oracle micro VM, AuraDB Free, Cloudflare Tunnel, v1.1.14, update timer every 15 minutes; every public check passed. Cloudflare: HSTS (6 months, zone-wide, no subdomains or preload) and a cache-bypass rule for `/api`.
- Public hosting built, agreed with Codex: `hosting/oracle/` (compose, systemd units, setup guide), the updater's hosted mode, `scripts/hosted_check.sh`, the hosted-only nginx include and a 16-request API ceiling, API driver limits, and the About note.
- BUG-003 fixed: Gunicorn logged the question when its watchdog killed a worker; the API now runs it at `--log-level critical`, and the smoke test forces a real timeout.
- Docker Hub mirror (D-030, FEATURE-014): after each release is published, `release.yml` starts `mirror.yml`, which copies the release's GHCR digests to `docker.io/hamzaazizai/medical-chatbot-api` and `-web` under the same version. The owner set the `DOCKERHUB_TOKEN` secret; the `DOCKERHUB_USERNAME` variable is `hamzaazizai`.
- Docker Hub pages (D-031): short descriptions and a shared overview in `docs/dockerhub/`, applied after every merge by `dockerhub-metadata.yml`, which also turns on immutable version tags; OCI labels on both images from the next release.
- Docker Hub categories set by the owner on both repositories (Machine learning & AI, Web servers, Databases & storage), read back from the API.
- v1.1.13 backfilled to Docker Hub (PR #58, mirror run 40508274098): both images have the same index digests as on GHCR, with the attestation manifest, and both repositories are public.

In progress:
- BUG-004 (release tag refused after a workflow change) is worked around, not fixed; choose a fix with the owner.

Broken or risky:
- The hosted site will be public without login (D-032): one API worker for everyone, questions visible to Cloudflare and Oracle, Aura pauses and Oracle reclamation, and the dataset's rights (A-01) unresolved.
- The Docker Hub token in Actions is admin-scoped (the owner's choice): a leak could delete the repositories (D-031).

Next:
- Owner: go through the Lane-B checklist in TESTING.md for the public site; watch the first automatic hosted update; check Oracle's idle-reclamation terms.
- Owner: check that the Docker Hub token has an expiry.

Do not touch:
- `.env` contents, real credentials, the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai`, LinkedIn. See CONSTRAINTS.md.

## Session: 2026-10-25 to 2026-10-26 (model: Claude Opus 5.5, claude-opus-5-5; councils with Codex/ChatGPT)

Done:
- Reworded answers built up to the owner's review (D-029, FEATURE-013): 10 pilot candidates in `pilot-data/rewordings/review.html` (2 pass every check); the API ships with an empty store, so nothing changes until fields are approved.
- Round 2 of the language-model check on the running configuration (D-027 addendum): quality passed, no new wrong-subject answers; reliability, latency and the strict safety-subset gate not met; the model stays on as the owner decided.
- `Cache-Control: no-store` on every API response, in Flask and nginx (D-029); language-model counters with denial reasons.
- Long answers show their own sections and numbered points, every word kept (D-028, FEATURE-012).
- The owner's stack runs v1.1.9 with the language model on: deployed by hand (the compose change), re-enrolled for automatic updates, `/api/health` ok, and a paraphrase routed by the model in 1.08 s.
- Step 4, by the owner's decision (D-027, FEATURE-011): the language model now reads questions at runtime (on by default in compose), with the rules as fallback, local confirmations first, refusals final, budgets and a breaker. Checked on a throwaway stack with the real model.
- Step 3 run on `gpt-oss:120b-cloud`: +36 points of understanding, but it failed the safety, reliability and latency gates, so no runtime change (D-026 outcome).
- Step 3 set (150 scenarios, frozen) and rule baseline: 68.9% complete frames held out, 12 wrong-subject answers.
- Step 3 of the language-model plan pre-registered (D-026, FEATURE-010): an offline experiment on `gpt-oss:120b-cloud`, with the protocol and bar fixed before any run.
- Dataset pilot, step 2 (FEATURE-009): an unreviewed local candidate list; 62 of the 451 unmatched names have a lexical lead, 389 none; nothing applied.
- Per-client spelling-suggestion budget (D-025), released in v1.1.7 and running on the owner's stack; checked end to end on a throwaway stack (the budget follows the forwarded client address).
- The owner's stack runs v1.1.6 with the plan fingerprint; the rollback drill also passed on v1.1.5 → v1.1.6.
- D35 closed as far as detection goes (D-023 addendum): a plan fingerprint in the graph and the dictionary; questions refused with 503 while they do not match.
- Rollback drill passed on a throwaway stack (FEATURE-007): restore after a failed step and after the updater process died.
- The owner's stack is enrolled and updates itself: it moved from v1.1.1 to v1.1.5 overnight (backup, re-import, readiness check each time, about 40 s of downtime), and `/api/health` is ok.
- Dataset pilot, step 1 (FEATURE-009): exact name overlap with MedlinePlus and the Disease Ontology is 31.5% of 658 diseases; nothing imported.
- D35 partially mitigated (D-023): one dictionary read at API start; the importer names one recovery for every partial outcome.
- Readiness route (D-022, FEATURE-008): `GET /health` reports whether the graph matches the dictionary; Docker and the updater use it.
- A-14: a 150 ms time budget on spelling suggestions (worst case about 160 ms instead of 1 s); saturation near the rate limit remains possible.
- A-13 fixed: spelling suggestions work for names that contain filler words or intent keywords (D-017 addendum).
- Stack updater (D-021, FEATURE-007): `scripts/update_stack.py` updates the local stack on each release, with backup and rollback.
- Automatic releases (D-019, D-020, FEATURE-006): one release per merge, in order; `release.yml` tags only after every gate.
- BUG-002 fixed: words inside a matched name are no longer read as intent keywords (D-018).
- Sourced aliases and confirmed typo suggestions (D-017, FEATURE-005).
- Guided conversation (D-015, D-016, FEATURE-004): structured replies, follow-ups, clarification, explained abstentions, suggestion chips, "Why this answer?", topic bar, emergency guidance.
- Professional UI redesign (D-014, FEATURE-003): clinical light and dark themes, example questions, typing indicator, styled errors, About card with graph counts.
- Removed the API token (D-013): no token field or `CHATBOT_API_TOKEN`; nginx rate-limits the API in Docker (FEATURE-002).
- Shared agent setup: `AGENTS.md` is the single instruction file for all coding agents (Codex reads it natively); `CLAUDE.md` imports it and the new shared `MEMORY.md` (D-012).
- Adopted the "Defend What You Ship" field guide: created this `docs/` set (decisions, alternatives, architecture, flow, constraints, threat, failure, data, testing, rollback, assumptions, dependencies, defense brief, one bug and one feature trace).
- Automatic merging: `.github/workflows/automerge.yml` merges a same-repository PR into `main` once every check on its head commit passes (PR #15).
- Knowledge-graph integrity fixes and a permanent integrity check in `scripts/evaluate_kg.py` (PR #14).
- CI/CD and MLOps pipelines (PR #13), release `v1.0.0` with public GHCR images, Vue 3 + Vite frontend (PR #12), per-module logging (PR #11), `.env` loading (PR #10), defect fixes D1–D41 (PRs #1, #8).
- Dataset review with Codex: no drop-in replacement for `medical.csv`; a MedlinePlus + Disease Ontology composite is worth a pilot (see ALTERNATIVES.md).

In progress:
- Nothing.

Broken or risky:
- `medical.csv` and `questions.json` have unknown redistribution rights (D30, ASSUMPTIONS.md A-01, A-02).
- Graph and dictionary publication are still two steps (D35): any plan mismatch is now detected and refused (D-023 addendum), but the readiness check and the answer queries are separate, so imports must still run with serving stopped, one at a time.
- Many client addresses together can still keep the single API worker busy; one address is bounded to about one second of suggestion work per minute (A-14, D-025).
- The language model runs before it met its pre-registered bar (D-027, the owner's decision): real questions go to Ollama's cloud, wrong interpretations remain possible, and other requests wait behind a model call of up to 2 s.

Next:
- Rewording: the owner reviews `pilot-data/rewordings/review.html`, writes `decisions.json`, runs `python scripts/reword_answers.py --approve decisions.json` and opens a PR with the store.
- Language model: Round 2 (fresh set, the running setup) passed quality and added no new wrong-subject answer, but missed reliability (98.1%) and latency (p95 1.56 s), and the safety-subset gate on one injection turn the rules also answer. Next round: tighten the prompt for role-override text, consider a longer timeout or a faster model, and use a fresh set again. Watch the new counters for budget denials.
- Optional: review `pilot-data/candidates.json` (local, unreviewed) and record evidence-backed decisions per candidate (equivalent, broader, narrower, related, rejected, uncertain) before any sourced dataset (D-011); rights and evaluation gates still apply. 389 names have no lexical lead and need another approach, likely manual.

Do not touch:
- `.env` contents, real credentials, the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai`, LinkedIn. See CONSTRAINTS.md.

Read first: ARCHITECTURE.md, CONSTRAINTS.md
