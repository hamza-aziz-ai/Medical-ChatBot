# FEATURE-010: Language-model understanding, step 3 (offline experiment)

**Goal.** Find out whether a language model routes questions better than the rules without adding unsafe answers, before any runtime change (D-026).

**Scope.** `docs/pilot/LLM-UNDERSTANDING.md` (protocol and results), `eval/understanding.jsonl` (synthetic set), a rule baseline scorer, `scripts/llm_understanding.py` (offline harness), their tests with a fake transport. Nothing in `api/`.

**Design.** Agreed with Codex in council: a routing frame, never an answer; candidates built locally; four configurations scored separately; the bar fixed before any run. See the protocol.

**Status.** Protocol pre-registered; set frozen and rules scored; the model harness is not built yet.

**Open questions.** Whether the bar is met; if so, step 4 is a separate decision.

## Log

- 2026-10-26: Owner chose `gpt-oss:120b-cloud` and accepted cloud hosting. Protocol and bar pre-registered (D-026).
- 2026-10-26: Set written (Claude 75, Codex 75), cross-reviewed and frozen (SHA-256 `33c6ac5e…`). Rule baseline on held-out turns: 124/180 complete frames (68.9%), 42/75 on paraphrase and multi-turn (56.0%), 12 wrong-subject answers (negation 4, unsupported 4, injection 3, mixed 1). The wrong-subject definition was fixed after the first baseline count and before any model run. Offline 313 passed, 12 skipped; live 325 passed.
