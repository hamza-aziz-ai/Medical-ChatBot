# HANDOVER

Read this first, then [CONSTRAINTS.md](CONSTRAINTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Newest entry on top. Update it at the end of every session.

## Latest session: 2026-10-25 (model: Claude Opus 5.5, claude-opus-5-5; councils with Codex/ChatGPT)

Done:
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
- The automerge path triggered by finished CI runs has not run on a real PR yet (A-07).
- Graph and dictionary publication are not one unit (D35).

Next:
- Optional: dataset pilot (MedlinePlus + DOID) behind a rights gate and the evaluation gate.

Do not touch:
- `.env` contents, real credentials, the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai`, LinkedIn. See CONSTRAINTS.md.

Read first: ARCHITECTURE.md, CONSTRAINTS.md
