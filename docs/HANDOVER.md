# HANDOVER

Read this first, then [CONSTRAINTS.md](CONSTRAINTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Newest entry on top. Update it at the end of every session.

## Latest session: 2026-10-25 to 2026-10-26 (model: Claude Opus 5.5, claude-opus-5-5; councils with Codex/ChatGPT)

Done:
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
- One client near nginx's rate limit can still keep the single API worker busy with long nonsense questions (A-14, reduced to about 160 ms each).

Next:
- Optional: a reviewed mapping of the 451 unmatched names before any sourced dataset (D-011); rights and evaluation gates still apply.

Do not touch:
- `.env` contents, real credentials, the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai`, LinkedIn. See CONSTRAINTS.md.

Read first: ARCHITECTURE.md, CONSTRAINTS.md
