# FEATURE-011: Language-model understanding at runtime (step 4)

**Goal.** Use the step-3 model in the running system, as the owner decided, with the safeguards agreed with Codex (D-027).

**Scope.** `api/understanding.py`, `api/chatbot_graph_logic.py` (`respond`, `respond_routed`, `declined_topic`), `api/app_logging.py`, `compose.yaml`, `.env.example`, `scripts/llm_understanding.py` (now imports the shared contract), `scripts/evaluate_kg.py` and `scripts/compose_smoke.sh` (switched off), the chat panel and About card (disclosure, provenance), tests.

**Design.** See D-027: candidates from the rules' matching, the topic only after the full follow-up check, local confirmations and vetoes first, per-pair queries, refusals final, everything else the rules; a 2 s total deadline, attempt budgets and a breaker; one worker.

**Status.** Built and checked on a throwaway stack; on by default in compose.

**Open questions.** A fresh-holdout run of this configuration against the D-026 bar; whether the budgets are too tight.

## Log

- 2026-10-26: Built. Throwaway stack with the real model: a paraphrase ("what does asthma feel like") and a negation were read correctly by the model, the cousin case made no call and abstained, an unreachable Ollama fell back to the rules in 217 ms, and the off switch restored the rules (a description for the paraphrase). `/health` took 1.64 s while a 1.88 s model call held the worker. Logs held outcomes and timings only.
- 2026-10-26: By the owner's choice, the page names no vendor: a generic note in the About card only, and a generic provenance line. Frontend 11 helper and 22 component tests passed.
- 2026-10-26: Counters (agreed with Codex): attempts, routed, unusable, failures by fixed category, budget denials by where they happen (client, global, table full) and breaker skips, in memory only; a cumulative line in `understanding.log` at most every 5 minutes when there is activity, plus one at shutdown. `admit()` now returns the denial reason. Only the offline harness can pass other budgets or breakers.
- 2026-10-26: Round 2 on a fresh frozen set (120 scenarios, 187 turns), the running configuration with limits bypassed in the harness only: 79–80% complete frames against the rules' 65%, +16.3 points on paraphrase and multi-turn, no new wrong-subject answers, 99.5% identical frames; 98.1% usable replies and p95 1.56 s miss the bar. 752 cloud calls including a lost first run (counted from Ollama's log).
