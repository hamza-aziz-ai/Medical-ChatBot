# FEATURE-010: Language-model understanding, step 3 (offline experiment)

**Goal.** Find out whether a language model routes questions better than the rules without adding unsafe answers, before any runtime change (D-026).

**Scope.** `docs/pilot/LLM-UNDERSTANDING.md` (protocol and results), `eval/understanding.jsonl` (synthetic set), a rule baseline scorer, `scripts/llm_understanding.py` (offline harness), their tests with a fake transport. Nothing in `api/`.

**Design.** Agreed with Codex in council: a routing frame, never an answer; candidates built locally; four configurations scored separately; the bar fixed before any run. See the protocol.

**Status.** Done: the bar was not met, so step 4 is not taken (D-026 outcome).

**Open questions.** Whether the bar is met; if so, step 4 is a separate decision.

## Log

- 2026-10-26: Owner chose `gpt-oss:120b-cloud` and accepted cloud hosting. Protocol and bar pre-registered (D-026).
- 2026-10-26: Set written (Claude 75, Codex 75), cross-reviewed and frozen (SHA-256 `33c6ac5e…`). Rule baseline on held-out turns: 124/180 complete frames (68.9%), 42/75 on paraphrase and multi-turn (56.0%), 12 wrong-subject answers (negation 4, unsupported 4, injection 3, mixed 1). The wrong-subject definition was fixed after the first baseline count and before any model run. Offline 313 passed, 12 skipped; live 325 passed.
- 2026-10-26: Harness built (`--model`, `--model --dev`); prompt frozen (SHA-256 `fa904c55…`) after one dev run. Held-out result, 3 runs, 632 calls: validated model 81.7–90.6% complete frames held out (rules 68.9%), 92.0–93.3% on paraphrase and multi-turn (rules 56.0%). Gates: quality pass; safety fail (6 new wrong-subject answers, all one scenario: "my cousin's condition" read as the previous topic); reliability fail (94.6% valid: 30 timeouts, 3 non-JSON, 1 HTTP error; 82.2% identical frames); latency fail (p50 0.74 s, p95 1.94 s). Rules-first gained 14.7 points but inherits the rules' wrong-subject answers. Offline 329 passed, 12 skipped; live 341 passed.
