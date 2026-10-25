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
- **Pilot, step 1 (2026-10-26, measurement only, agreed with Codex in council):** `scripts/dataset_pilot.py` measured exact name overlap: 207 of 658 diseases (31.5%) in either source, 451 in neither (docs/pilot/DATASET-PILOT.md). Most unmatched names are translations without a standard English form. Nothing was imported; the next step would be a reviewed mapping of the unmatched names, then the rights and evaluation gates.

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


## D-015: Guided conversation with structured replies, without a language model

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5) + Codex council; owner approved steps 1 and 2
- **Context:** Every question was answered in isolation: no follow-ups, no clarifying questions, and one fixed abstention sentence for every kind of miss.
- **Options:**
  1. keep plain text replies and add heuristics in the page
  2. a structured reply (status, reason, grouped answers, topic, interpretation, options) with `message` kept, and a page-held topic sent back with the next question
  3. server-side conversation sessions
- **Chosen:** 2
- **Why:** Keeps the API stateless and the questions unlogged, keeps every answer a template over graph facts, and lets the page offer follow-ups, clarifications and "Why this answer?".
- **Trade-off:** A larger reply contract to maintain; the evaluator and safety tests now check `status` instead of one fixed sentence.
- **Revisit if:** a language model takes over understanding questions (step 3).

## D-016: Answerable intents are written by the importer, not looked up at runtime

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); Codex council (Codex failed before the last point; cause unknown), then the LLM council fallback
- **Context:** Suggestion chips must only offer questions the graph can answer. A per-request lookup could delay an answer past the browser timeout (connect 10 s, acquisition 60 s, lazy reads are not bounded by a 1 s query timeout).
- **Options:**
  1. a per-request Cypher lookup with bounded waits
  2. one Cypher query at API start, with retries
  3. the importer writes each disease's answerable intents into `entities.json`
- **Chosen:** 3
- **Why:** The facts are fixed when the graph is built. No database call at start or per request, no new timeouts, and the existing dictionary check plus a live chip check in the MLOps gate keep it in step with the graph.
- **Trade-off:** `entities.json` grows (about 4,800 lines); a missing table means no chips until the importer runs again.
- **Revisit if:** the graph is updated without re-running the importer.

## D-017: Sourced aliases and confirmed typo suggestions

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); design agreed with Codex (job-17)
- **Context:** Only exact dictionary names were recognised: "whooping cough" or "asthama" got "I couldn't find a disease or symptom".
- **Options:**
  1. silent fuzzy matching
  2. a sourced alias list plus typo suggestions the user must confirm
  3. leave matching exact
- **Chosen:** 2
- **Why:** Aliases from MedlinePlus "Also called" lists are exact equivalents, so they apply directly and are shown in "Why this answer?". A misspelling is only ever offered ("Did you mean asthma?"), because a near-miss can be a different disease.
- **Trade-off:** The alias list is small and maintained by hand; the typo cutoff (0.8, stdlib `difflib`) was tuned on a small reviewed set.
- **Revisit if:** a curated synonym source (for example the Disease Ontology) is adopted.
- **Addendum (2026-10-25, A-13, agreed with Codex in council):** candidates are now every 1-3-word window of the question that holds at least one word that is neither filler nor an intent keyword, deduplicated in order, keeping inner punctuation; each suggested name keeps the window it matches best (scored as difflib does) and names keep first-seen order. Names containing keywords or filler ("deep palm infection", "face of bruises") are now suggested whole: 69 of 69 one-swap typos of such names, against 14 before, with complete corrected questions. A filler word at a window's edge must also be a word of the suggested name; otherwise "symptoms of pneumonia" (pneumonia is quarantined) would offer "shock pneumonia" through the window "of pneumonia", which the evaluation's mandatory abstention caught. A 12-token cap was rejected because it broke ordinary long questions; global ordering by score was considered and not needed. Cutoff, limit of 3 and confirm-only are unchanged.
- **Addendum (2026-10-26, A-14, the owner chose a time budget; agreed with Codex in council):** matching stops at a cooperative 150 ms deadline checked before each window and offers what it found; a window already started finishes, so it is not a hard ceiling. Windows now run position-first (every size at a position before the next), so a cut-off scan drops the end of the question rather than every single-word typo, and an intent keyword at a window's edge must also be in the suggested name, so a cut-off scan cannot turn "what causes adbominal infection" into "what abdominal infection". Measured: a normal typo question 42 ms, a 16-token question 101 ms, a 500-character question of unknown words 158 ms (was about 1 s). Rate limits and concurrency are unchanged, so saturation by one client near the rate limit remains possible (A-14).

## D-018: Words inside a matched name are not intent keywords

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); design agreed with Codex in council
- **Context:** BUG-002. Keywords were matched across the whole question, so "infection" inside "deep palm infection" added the unsupported "who gets it" intent and every question about three diseases abstained.
- **Options:**
  1. mask matched names before keyword matching, everywhere `classify_with` runs
  2. filter keyword matches by position against entity spans
  3. remove "infection" from the keyword list
- **Chosen:** 1, except that a name that is itself a keyword ("phenomenon") stays readable as one
- **Why:** One change in the shared classifier fixes answers, suggestion chips, the evaluator and the chip check together. Masking with `#` keeps `check_words` unchanged and stops a keyword phrase bridging a name. Option 2 gives the same result with more code; option 3 would stop "who gets infections?" style questions from being recognised as unsupported. The exception keeps today's answer for "what is the phenomenon of asthma", the only name equal to a keyword.
- **Trade-off:** On the template grid (every disease and symptom times the 7 suggestion questions), exactly 21 classifications change, all for the 3 affected diseases; arbitrary questions were not measured exhaustively.
- **Revisit if:** a name equal to a keyword is added, or keywords move to a learned intent model.

## D-019: Release automatically once every gate passes

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); design agreed with Codex in council (7 exchanges)
- **Context:** The owner asked for releases without pushing tags by hand. Merges by `automerge.yml` and tags pushed with the workflow token start no other workflows (GitHub runs only `workflow_dispatch` and `repository_dispatch` from that token).
- **Options:**
  1. tag on every merge, then dispatch `release.yml`
  2. a planner that releases the current state of `main`, calling `release.yml`, which tags only after its gates pass
  3. keep manual tags
- **Chosen:** 2. `autorelease.yml` runs `scripts/next_release.py` and calls `release.yml` with a new `tag` and `sha`; the tag is created in `publish`, after the gates and the smoke test.
- **Why:** A failed release consumes no version and leaves nothing half-tagged. The planner is state-based (main versus the last published release), so duplicate or replaced runs are harmless. Images are pushed under tags unique to each attempt, so retries never overwrite (CONSTRAINTS.md). An incomplete publication stops automation until the owner acts (ROLLBACK.md).
- **Trade-off:** Releases are batched: one release covers every shippable merge since the last published one, and a merge that lands during a running release is included in the next. Patch by default; `release:minor` or `release:major` labels, or the manual `bump` input, choose more.
- **Revisit if:** the owner wants exactly one release per merge, or a hosted deployment is added.
- **Rollout:** this change adds manual starts only; v1.1.0 is cut through it; the trigger after automerge is enabled separately once the owner accepts batching. This is the owner's standing authorization for the publisher to create release tags.

## D-020: One release per merge

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); design agreed with Codex in council (2 exchanges)
- **Context:** D-019 proposed batching (one release for every shippable merge since the last). The owner chose one release per merge instead.
- **Options:**
  1. one run releases several merges through a matrix of `release.yml` calls
  2. one run releases the oldest unreleased merge, then starts the next run after a success
- **Chosen:** 2. `next_release.py` picks the oldest first-parent commit after the last published release that changed shipped files; a merge counts as released only through a published release, so a merge under an abandoned tag is released again under the next version. A `continue` job, the only one allowed to start workflows, starts the next run after a successful release. Supersedes the batching in D-019; everything else in D-019 stands.
- **Why:** GitHub does not guarantee matrix job order, and several `release.yml` calls in one run would collide on the `eval-report` artifact name. Chained runs keep releases in merge order: each is planned only after the previous one is published.
- **Trade-off:** About 15 minutes per release, one after another. A merge whose release keeps failing blocks later releases until the owner publishes a later commit by hand (`release.yml` with `tag` and `sha`), which deliberately skips separate releases for the merges in between. A change and its revert are two releases.
- **Bootstrap:** everything merged before this is released by the owner as one `v1.1.0`; automatic runs pass `--require-baseline v1.1.0` and refuse to drain the older backlog one by one.
- **Revisit if:** releases queue up faster than they publish.

## D-021: Update the local stack automatically when a release is published

- **Date:** 2026-10-25; **Model:** Claude Opus 5.5 (claude-opus-5-5); design agreed with Codex in council (4 exchanges)
- **Context:** Releases are now automatic (D-019, D-020). The owner asked for the running stack to update and restart itself. It runs on the owner's Windows machine, bound to loopback, with no inbound access.
- **Options:**
  1. a self-hosted GitHub runner that deploys from the release workflow
  2. a container auto-updater (for example Watchtower) following a moving tag
  3. a scheduled script on the machine that polls GitHub for releases
- **Chosen:** 3. `scripts/update_stack.py`, run every 15 minutes by a Windows scheduled task while the owner is signed in. Read-only enrolment records a running published release. Each update pulls first, then, in a short maintenance window, stops the stack, takes and checks an offline backup of the graph volume, re-imports with the new image, starts the new images and checks health; a journal with phases lets any failure or crash restore the previous release, restoring the backup only once it was verified. A release whose `compose.yaml` differs from the enrolled one is not deployed automatically.
- **Why:** No inbound access, no new secrets and no runner on a public repository. A compose file can grant host access, so only an enrolled one runs unattended. The backup is required before any import on a real database (CONSTRAINTS.md), and stopping the API during the import avoids an old dictionary answering against a new graph.
- **Trade-off:** About a minute of downtime per release (backup 5 s and restore 3 s measured on a small volume; the full cycle is not yet measured). Updates happen only while the owner is signed in with Docker Desktop running. A release that changes `compose.yaml` needs the owner's review and a new enrolment.
- **Revisit if:** the app is hosted somewhere else, or releases come faster than about one per 15 minutes.

## D-022: A readiness route that knows the graph is loaded

- **Date:** 2026-10-26; **Model:** Claude Opus 5.5 (claude-opus-5-5); the owner chose a GET route; design agreed with Codex in council (2 exchanges)
- **Context:** Docker's API healthcheck only opened the port, so an empty, stale or mismatched graph looked healthy, and the stack updater could only infer health from one question.
- **Options:**
  1. GET /health, used by Docker's healthcheck and the updater
  2. a script inside the container with no HTTP route
- **Chosen:** 1. `GET /health` returns 200 `{"status": "ok"}` only while the graph holds exactly the dictionary's diseases, all stamped with the dictionary's CSV hash (one non-retrying READ with a 1 s timeout, counting importer-owned diseases and those with the hash), else 503 `{"status": "unavailable"}`. It logs nothing on success and a fixed category on failure. The Dockerfile's healthcheck calls it (4 s HTTP, 5 s Docker timeout); `compose.yaml` is unchanged so the owner's enrolment stays valid. Release manifests carry `capabilities.health`; the updater requires `/api/health` only for releases that have it, so rolling back to older releases still works.
- **Why:** It catches an empty graph, a wrong-sized or differently sourced graph and unstamped diseases, which the old check missed, for the cost of one count query.
- **Trade-off:** It does not prove relationships, importer freshness or clinical accuracy; the evaluation and the updater's question probe still cover more. "Unhealthy" is a signal: Docker does not repair the data. The timeouts are not an end-to-end deadline, because connecting has its own limits.
- **Revisit if:** the API gains a second worker or a real deployment with an orchestrator that restarts on health.

## D-023: Graph and dictionary publication stays two steps, with detection and one recovery (D35)

- **Date:** 2026-10-26; **Model:** Claude Opus 5.5 (claude-opus-5-5); agreed with Codex in council (2 exchanges); the owner asked for D35 to be addressed
- **Context:** The importer commits the graph, then replaces `entities.json`. A failure or crash in between, or an unknown commit outcome, leaves a graph and a dictionary from different imports; a running API also keeps the dictionary it read at start.
- **Options:**
  1. a two-phase commit or a roll-forward that keeps the staged file
  2. keep two steps, make every mismatch we can see visible, and give one recovery for all partial outcomes
- **Chosen:** 2, recorded as **partially mitigated**. The API now reads the dictionary once at start, so the classifier, suggestions and readiness cannot mix two versions (a start-up race Codex reproduced). The importer reports a failed publication after commit and an unknown commit outcome (`IncompleteCommit`) with the same instruction: fix the publication error, rerun the same import, then restart the API and check `GET /health` before serving.
- **Why:** True atomicity across a Neo4j transaction and a file needs a two-phase commit, which a local prototype does not justify. A re-run is idempotent and takes seconds.
- **Trade-off:** Readiness detects a dictionary from a different CSV or with a different disease count, but not a different importer version on the same CSV, which can change entity sets, relationships and suggestions; equal counts do not prove equal names. `/health` reporting unavailable does not stop `/` from answering. Imports must run one at a time, during maintenance. In Docker the updater imports with the image it then starts, and its rollback restores the verified backup rather than re-importing.
- **Revisit if:** the importer logic changes without the CSV, or the API serves real users; then store a dictionary fingerprint with the graph and refuse to answer while not ready.
- **Addendum (2026-10-26, done; the owner chose refusal; agreed with Codex in council):** one `plan()` builds the graph data and the dictionary and fingerprints them together with the importer's write queries (`plan_sha256`, SHA-256 of canonical JSON, unordered collections sorted). The fingerprint goes into `entities.json` and onto every importer-owned disease. Readiness now requires every owned disease to carry the fingerprint of the dictionary the API read at start, so a different importer on the same CSV, a changed description or a reversed relationship is detected, and `/` refuses questions with 503 while not ready (one extra readiness query per question, measured at 4 ms median, 8 ms at the 95th percentile). Still true: publication is two steps, the readiness check and the answer queries are separate (imports run with serving stopped, one at a time), damage to the live graph after an import is left to the evaluator, and mixed versions are supported only through the updater's paired backup and image rollback. A graph imported before this change is not ready until re-imported; the updater always re-imports.

## D-025: A per-client budget for spelling suggestions

- **Date:** 2026-10-26; **Model:** Claude Opus 5.5 (claude-opus-5-5); the owner chose a per-client budget; design agreed with Codex in council (3 exchanges)
- **Context:** A-14: the 150 ms per-call deadline (D-017 addendum) still let one client keep the single API worker busy with long questions of unknown words at nginx's 10 requests per second.
- **Options:**
  1. a per-client budget of spelling-suggestion time
  2. a lower nginx rate limit for everyone
  3. accept the risk
- **Chosen:** 1. Each client address gets a token bucket of elapsed fuzzy-matching time: a one-second burst, refilled at one second per minute (starting values). A request may spend at most the smaller of 150 ms and its remaining credit, measured from before the candidate windows are built; the time actually used is charged even on errors, and overruns become debt. Without credit, the question gets the plain "I couldn't find a disease or symptom I know" reply; exact names, aliases, follow-ups and answers are unaffected. One lock serialises the budgeted section. At most 10,000 addresses are kept, in memory only; only idle, fully refilled ones are forgotten, never a client in debt.
- **Why:** It targets the expensive work without slowing normal users, and bounds one client's sustained fuzzy work to about one second per minute.
- **Trade-off:** Identity comes from `X-Real-IP`, which nginx overwrites and which the API trusts only where the image sets `TRUST_PROXY_HEADER=1`; anything inside the Compose network is trusted. Requests resolving to the same address share credit (on Docker Desktop, possibly every browser on the host; not yet observed). Many addresses, restarts, several workers and non-fuzzy request cost are outside this budget.
- **Revisit if:** the API is exposed beyond this machine, or real users report missing suggestions.
