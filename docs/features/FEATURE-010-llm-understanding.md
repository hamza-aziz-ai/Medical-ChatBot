# FEATURE-010: Language-model understanding, step 3 (offline experiment)

**Goal.** Find out whether a language model routes questions better than the rules without adding unsafe answers, before any runtime change (D-026).

**Scope.** `docs/pilot/LLM-UNDERSTANDING.md` (protocol and results), `eval/understanding.jsonl` (synthetic set), a rule baseline scorer, `scripts/llm_understanding.py` (offline harness), their tests with a fake transport. Nothing in `api/`.

**Design.** Agreed with Codex in council: a routing frame, never an answer; candidates built locally; four configurations scored separately; the bar fixed before any run. See the protocol.

**Status.** Protocol pre-registered; set, baseline and harness not built yet.

**Open questions.** Whether the bar is met; if so, step 4 is a separate decision.

## Log

- 2026-10-26: Owner chose `gpt-oss:120b-cloud` and accepted cloud hosting. Protocol and bar pre-registered (D-026).
