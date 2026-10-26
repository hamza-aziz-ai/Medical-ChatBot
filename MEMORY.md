# MEMORY

Shared, durable memory for every coding agent in this repository. Read it at the start of a session. Add a dated bullet when you learn an owner preference, a correction or a non-obvious fact that the code and `docs/` do not already record; fix or delete bullets that turn out to be wrong. Never store secrets or session-only details. Current status lives in [docs/HANDOVER.md](docs/HANDOVER.md), not here.

## Owner preferences

- 2026-10-25: Pull requests merge automatically through `automerge.yml` once every check passes; no reviews, and agents never merge by hand.
- 2026-10-25: When committing the owner's own edits, commit them as-is and do not call out individual changes.
- 2026-10-25: Never hard-wrap prose in Markdown or generated pages; one line per paragraph or bullet.
- 2026-10-25: Write enumerations (options, steps, alternatives) as real Markdown numbered or bulleted lists, never inline as "1) … 2) …" on one line.
- 2026-10-25: Follow the "Defend What You Ship" field guide; the rules are in AGENTS.md and the files in `docs/`.
- 2026-10-25: "Council with Codex" means Claude Code discusses with the owner's Codex session named `Medical-ChatBot` (codex-claude-council plugin, `council_join`) until both agree, then implements, opens a PR and lets automerge merge it.
- 2026-10-25: If the codex-claude-council plugin fails for any reason (Codex error, disconnect, timeout, lock), fall back to the `/llm-council` skill for the same question or the unresolved point, and say so.
- 2026-10-25: After significant changes the owner may ask to "update the two artifacts": the claude.ai pages Solution Architecture and Software & System Design, published by Claude Code.
- 2026-10-26: The page must not name vendors, models or the tech stack to end users. Privacy notes stay generic ("an external AI service"), in the About card only.
- 2026-10-25: Never touch the GitHub profile repository `hamza-aziz-ai/hamza-aziz-ai` or LinkedIn from this project, never read `.env`, and never repeat the old (rotated) Neo4j password.

## Project facts

- 2026-10-25: Development machine is Windows 11 (PowerShell and Git Bash); the Python virtual environment is `.venv` (Python 3.14); Node 24 locally; Docker Desktop is available for disposable Neo4j containers.
- 2026-10-25: `.gitignore` ignores `[Ss]cripts` (a virtualenv pattern); `!/scripts/` un-ignores the repository's own `scripts/` folder.
- 2026-10-25: `load_dataset(path=CSV_PATH)` binds its default at definition time, so tests must patch `builder.load_dataset`, not `CSV_PATH`.
- 2026-10-25: Workflows use YAML anchors for path lists; lint with actionlint 1.7.12 or newer (1.7.7 rejects anchors).
- 2026-10-25: Merges made by `automerge.yml` use the workflow token, so the `main` push runs of the other workflows do not start again. The same holds for tags pushed with that token; only `workflow_dispatch`, `repository_dispatch` and `workflow_run` chains start from it, which is why `autorelease.yml` calls `release.yml` instead of pushing a tag.
- 2026-10-25: The local `gh` login lacks the `read:packages` scope; check GHCR images with the anonymous token endpoint instead. Both images are public.
- 2026-10-25: In claude.ai artifact pages, scrolling inside the frame does not work in browser automation; navigate to `#anchor` ids (figures A5–A7 have ids) to check diagrams.
- 2026-10-26: Ollama's request log (`%LOCALAPPDATA%\Ollama\server.log`, `[GIN]` lines with time, status and latency, no content) gives exact counts of cloud model calls; use it to account for the owner's call allowance.
