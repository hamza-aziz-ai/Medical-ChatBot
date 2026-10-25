# DECISIONS

One entry per meaningful decision: context, options, choice, why, trade-off, when to revisit. Newest at the bottom. Draft the entry before making the change. Rejected options in more depth: [ALTERNATIVES.md](ALTERNATIVES.md). "Council" means Claude and Codex (ChatGPT) reviewed it independently and agreed.

## D-001: Answer from a knowledge graph with fixed templates

- **Date:** original project (observed 2026-10-25); **Model:** original authors; reviewed by Claude Opus 5.5 + Codex
- **Context:** A medical Q&A bot must not invent answers.
- **Options:**
  1. graph + templates
  2. generative model
  3. retrieval over stored Q&A
- **Chosen:** 1
- **Why:** Every answer is an inspectable query result.
- **Trade-off:** Only questions matching the dictionaries and keywords are understood.
- **Revisit if:** understanding phrasing matters more than inspectability.

## D-002: Remove the similarity fallback and abstain instead

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5) + Codex council
- **Context:** When the graph had no answer, a Siamese-LSTM (trained on Kaggle Quora Question Pairs) picked the most similar stored questiondoctors.com question and returned its answer. Its weights were missing, the selection always picked record 0, and the ranking ignored the query (D1, D2, D23).
- **Options:**
  1. repair and retrain
  2. remove and abstain
- **Chosen:** 2
- **Why:** Returning another patient's answer to an unrelated question is unsafe; retraining is not reproducible (D21).
- **Trade-off:** More "I cannot answer" replies.
- **Revisit if:** a validated, licensed retrieval source and evaluation exist.

## D-003: Quarantine bad data instead of guessing

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** 72 malformed list fields and 8 conflicting disease names in the CSV.
- **Options:**
  1. repair heuristically
  2. drop whole rows
  3. exclude the bad field or name and report it
- **Chosen:** 3
- **Why:** Keeps every valid fact without inventing any.
- **Trade-off:** Some diseases answer fewer intents.
- **Revisit if:** a curated source replaces the CSV.

## D-004: The importer owns and replaces a marked snapshot

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** Re-imports left stale facts; imports could overwrite unrelated data.
- **Options:**
  1. MERGE upserts
  2. wipe the database
  3. mark owned data and replace only it, refusing collisions
- **Chosen:** 3
- **Why:** Removed facts disappear; foreign data is never touched.
- **Trade-off:** Collisions need manual reconciliation.
- **Revisit if:** several importers must share one graph.

## D-005: Shared Bearer token and exact-origin CORS (token superseded by D-013)

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** The API was open to any caller.
- **Options:**
  1. user accounts
  2. shared token
  3. network isolation only
- **Chosen:** 2, plus loopback binding
- **Why:** Proportionate for a local prototype.
- **Trade-off:** One leaked token opens the API until rotated.
- **Revisit if:** there are real users (Lane B).

## D-006: Vue 3 + Vite with an in-house chat panel

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** Vue 2 end of life; Vue CLI only installed on Node 18; 88 dependency alerts.
- **Options:**
  1. Vue 3 + keep a widget library
  2. Vue 3 + small own panel
  3. stay on Vue 2
- **Chosen:** 2
- **Why:** Accessible, text-only rendering, no abandoned widget; alerts fell to 0.
- **Trade-off:** We maintain the chat panel ourselves.
- **Revisit if:** the UI grows beyond one chat panel.

## D-007: Path-filtered CI, graph MLOps, tag-gated delivery

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** CI ran everything on every push; no delivery.
- **Options:**
  1. one orchestrator with change detection
  2. native path filters per workflow
- **Chosen:** 2
- **Why:** Docs-only changes start nothing; no custom diff code to maintain.
- **Trade-off:** Required status checks would need an always-running gate job.
- **Revisit if:** branch protection with required checks is enabled.

## D-008: nginx keeps no access or error log

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** Both logs would contain the question from `?search=`.
- **Options:**
  1. severity filtering
  2. redaction
  3. discard both
- **Chosen:** 3
- **Why:** Severity filtering does not redact; discarding is the smallest safe change.
- **Trade-off:** nginx problems are not logged.
- **Revisit if:** questions move out of the URL (for example a POST body).

## D-009: Skip self-links and repeated departments; independent integrity check

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** Audit found 5 self-complications and an oncology self-parent; plan equality cannot catch shared mistakes.
- **Options:**
  1. fix data by hand
  2. fix in the importer and check invariants independently
- **Chosen:** 2
- **Why:** Fixes every future import and catches what plan equality cannot.
- **Trade-off:** More checks to maintain in `evaluate_kg.py`.
- **Revisit if:** the schema changes.

## D-010: Merge automatically when every check passes

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (owner's instruction)
- **Context:** Owner wants no review step; CI is the gate.
- **Options:**
  1. human review
  2. GitHub auto-merge with required checks
  3. workflow that merges after checks
- **Chosen:** 3
- **Why:** Works with path-filtered workflows and no branch protection; docs-only PRs also merge.
- **Trade-off:** A wrong but passing change by a collaborator merges unreviewed.
- **Revisit if:** collaborators are added or real users depend on main.

## D-011: Keep medical.csv for now; pilot a sourced composite later

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 + Codex council
- **Context:** The CSV's source, licence and clinical review are unknown (D30).
- **Options:** see ALTERNATIVES.md, A-DATA
- **Chosen:** keep, and evaluate MedlinePlus + Disease Ontology behind rights and evaluation gates
- **Why:** No reviewed candidate covers all seven intents with a redistributable licence.
- **Trade-off:** The rights question stays open while the CSV remains.
- **Revisit if:** the pilot passes both gates.

## D-012: One shared instruction file and memory for all coding agents

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5)
- **Context:** The owner wants Codex and other agents to follow the same rules as Claude Code, plus a shared project memory.
- **Options:**
  1. separate `AGENTS.md` and `CLAUDE.md` kept in sync by a CI check
  2. `AGENTS.md` as the single source, with `CLAUDE.md` importing it
  3. generate one from the other
- **Chosen:** 2, plus a committed `MEMORY.md` imported the same way
- **Why:** Claude Code's `@file` import means there is nothing to drift and nothing to check; Codex reads `AGENTS.md` natively.
- **Trade-off:** Instructions must be written for every agent, not in Claude-specific terms.
- **Revisit if:** an agent needs instructions the others must not follow.

## D-013: Remove the API token; rate-limit in nginx instead

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); owner's choice
- **Context:** The owner asked why users must paste a token. The API is read-only over public data, listens on this machine only, and calls no paid service; the token (D-005) protected little and added friction and a secret to manage.
- **Options:**
  1. remove the token; keep loopback binding and input limits; add an nginx rate limit
  2. make the token optional, checked only when set
  3. keep it
- **Chosen:** 1
- **Why:** The real risks (flooding, abuse of a public endpoint) are not addressed by a shared secret every user must know; a rate limit addresses flooding, and the API is not public.
- **Trade-off:** Anyone on this machine can query the API. Exposing it beyond the machine now requires adding real authentication and HTTPS first (CONSTRAINTS.md).
- **Revisit if:** the bot is hosted for other people.

## D-014: A clinical, self-contained UI design

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5)
- **Context:** The owner asked for a more professional UI.
- **Options:**
  1. hand-written CSS with design tokens and system fonts
  2. a UI framework or component library
  3. web fonts and icon packs from a CDN
- **Chosen:** 1
- **Why:** No new dependency and no external request (privacy, and the CSP only allows the page's own origin); the chat page is small enough that a library adds more than it saves.
- **Trade-off:** We maintain the styles ourselves; the look depends on the user's system font.
- **Revisit if:** the UI grows into several pages or needs complex components.

