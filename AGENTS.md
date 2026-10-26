# AGENTS.md

Instructions for every coding agent working in this repository (Codex, Claude Code and others). This file is the single source: `CLAUDE.md` only imports it, so edit this file, never a copy. Also read [MEMORY.md](MEMORY.md), the shared project memory.

## Project

Mr. Healthcare: a rule-based medical question-answering chatbot (B.Tech project). Vue 3 + Vite frontend (`frontend/`), Flask API (`api/`), Neo4j knowledge graph built from `api/data/medical.csv` by `api/build_medicalgraph.py`. A language model (`gpt-oss:120b-cloud` through Ollama) may read questions at runtime but never answers them; answers come only from the graph, and unanswerable questions get an explicit abstention (D-027). Map: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Setup and commands: [README.md](README.md). Checks and expected output: [docs/TESTING.md](docs/TESTING.md).

## Defend What You Ship

This project follows the "Defend What You Ship: AI Field Guide v2". The `docs/` folder implements it.

- Start every session by reading `docs/HANDOVER.md`, then `docs/CONSTRAINTS.md` and `docs/ARCHITECTURE.md`. Obey CONSTRAINTS.md; stop and ask before breaking any rule in it.
- Before a non-trivial change, explain the plan and the alternatives, and draft a `docs/DECISIONS.md` entry (context, options, choice, why, trade-off, revisit-if, date, model name and version). Record rejected options in `docs/ALTERNATIVES.md`.
- One logical change per commit, with a message that says what changed and why. Keep requests small; split anything that cannot be named in one sentence.
- Comment non-obvious logic with intent and assumptions (WHY notes, invariants), never restated syntax.
- Run the checks in `docs/TESTING.md` and report the real output.
- Log every new dependency and every secret touched in `docs/DEPENDENCIES.md` before adding it; scan diffs for keys, tokens and `.env` contents. Never read `.env`.
- Keep `docs/FLOW.md`, `DATA.md`, `THREAT.md`, `FAILURE.md` and `ROLLBACK.md` current when a change affects them. Trace each bug in `docs/bugs/BUG-NNN-*.md` and each feature in `docs/features/FEATURE-NNN-*.md` (append-only log).
- At the end of each task, list what was assumed but not verified in `docs/ASSUMPTIONS.md`.
- End every session by updating `docs/HANDOVER.md` (newest entry on top: Done, In progress, Broken or risky, Next, Do not touch, with model and date).
- `docs/defense/DEFENSE-medical-chatbot.md` is the owner's adopted whiteboard brief: keep it current when the system changes.
- Markdown files: never hard-wrap prose; one line per paragraph or bullet.

## Delivery

- Work on a branch, open a pull request into `main`, and let `.github/workflows/automerge.yml` merge it once every check passes. Do not merge by hand and do not request reviews.
- Never push to `main` directly, force-push, rewrite published history, or push release tags by hand unless the owner asks. Release tags are created only by `release.yml` after every gate passes; `autorelease.yml` decides when (D-019).

## Memory

- Read `MEMORY.md` at the start of a session. When you learn something durable (an owner preference, a correction, a non-obvious project fact), add or update one dated bullet there; delete entries that turn out to be wrong. Never store secrets, and link to `docs/` instead of duplicating it.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
