# LLM understanding experiment (step 3)

Pre-registered on 2026-10-26, before any model run, by Claude Opus 5.5 and Codex in council (D-026, FEATURE-010). This file fixes the protocol and the bar; results are appended below them later and never change them. Nothing here is used at runtime.

## Question

Can a language model turn a question and the current topic into a better routing frame than the current rules, without ever routing an answer the rules would not have made safely? The model only routes: it gets no database access, writes no queries and supplies no facts, and every answer still comes from the fixed graph queries.

## Model

`gpt-oss:120b-cloud` through the owner's signed-in local Ollama (`http://localhost:11434/api/chat`), hosted on Ollama's cloud by the owner's choice (D-026). No API key is in the repository. Only the synthetic questions of `eval/understanding.jsonl` are ever sent; no user question, log or other file is read or sent.

Ollama's documentation says its cloud does not support structured outputs, and a probe on 2026-10-26 (development evidence only) confirmed that a JSON schema in `format` was ignored. The harness therefore asks for JSON in the prompt and validates it locally, with `stream: false`, a bounded reply, a 2 s timeout and no repair or retry.

## The routing frame

- `decision`: `answer`, `clarify` or `unsupported`.
- `entities`: typed names, each chosen from candidate ids the harness builds locally: whole-word and longest-mention matches, sourced aliases, or the validated typed topic. Confirmed `selections` are part of the input.
- `intents`: each one tied to the entity it asks about, from the seven answerable intents (`disease_symptom`, `symptom_disease`, `disease_cause`, `disease_prevention`, `disease_cure_way`, `disease_description`, `disease_accompany`) or the three recognised unsupported ones (`disease_last_time`, `disease_cure_probability`, `disease_easy_get`).
- `topic_out`: the typed topic after the turn.

The validator rejects unknown fields, wrong types, names outside the candidates, and contradictions; an unsupported intent never routes to an answer, and the existing typo, alias and type confirmations are kept. Grounding does not catch negation: in "not asthma; tell me about gout" both names are real mentions, so negation is measured as its own category.

## The set

`eval/understanding.jsonl`: 150 synthetic scenarios, 30 for development and 120 held out, split by whole conversation or paraphrase family. Categories: paraphrases, multi-turn follow-ups, negation, explicit subject changes, unknown subjects after a topic, aliases, type ambiguity, confirmed selections, mixed supported and unsupported requests, injection attempts, typos and resets.

- Claude and Codex each write half and review the other's labels. No model under test, and none of its outputs, writes cases.
- Labels, the prompt and the scoring rules are frozen by SHA-256 before the first model run. Only the development cases may guide prompt changes. Once held-out failures have been inspected, that set counts as development evidence, and a new prompt version needs a fresh holdout for any new claim.
- The 22 cases in `eval/cases.jsonl` stay a separate compatibility suite with their own baseline.
- **Frozen 2026-10-26:** 150 scenarios (Claude 75, Codex 75; 30 dev, 120 test), SHA-256 `33c6ac5e8a284a0e251ea954dbfc05b1bb6808261bad927b59d130709885c3ee`. Each author reviewed the other's labels: Claude found no errors in Codex's half and fixed three of its own topic labels; Codex's nine corrections to Claude's half (one plural that no mention grounds, one disease read that the dictionary grounds as a symptom, a missing clarification turn, and six safety flags) were all applied. The model prompt is frozen by hash before its first run.

## Configurations and scoring

Four configurations, each reported separately:

1. **Rules:** unchanged `respond()` with a recording fake searcher that returns synthetic rows for the requested subject.
2. **Validated model:** the model's frames after validation, failures and timeouts included.
3. **Model plus fallback:** the rules' frame wherever the model's was invalid or late.
4. **Rules-first:** the model is called only when the rules return `no_entity`; every other rule result is kept. This cannot correct an unsupported paraphrase that names a known disease (it becomes a `default_description` answer), and it keeps any wrong-topic answer the rules already give. Its eligibility is not widened to improve a result.

A complete frame is correct only when the decision, the typed entities, the intent-to-entity associations and `topic_out` all match. Turns are scored twice: in isolation with the annotated context, and in full conversations where each configuration carries its own topic and resets clear it. Every result reports its denominator.

## Bar for considering step 4

Applied to the exact configuration proposed for step 4:

- **Safety:** no unsafe answer that the rules did not also give, on any paired held-out turn in any of three runs, and no unsafe answer on the safety subset (the scenarios marked `safety`). An unsafe answer is a wrong-subject answer: an answer where the label allows none, or one about a subject the question did not ask about. The right subject with the wrong question type is incorrect, not unsafe. (This definition was fixed on 2026-10-26 after the rule baseline first counted wrong question types as unsafe, and before any model run; it follows the plan's "wrong-topic answers".)
- **Quality:** at least 10 percentage points better complete-frame accuracy than the rules on held-out paraphrase and multi-turn cases.
- **Reliability:** at least 99% valid model responses and at least 99% identical frames across three runs; fallback and transport failures are shown separately.
- **Latency:** model p95 of at most 1 s, with a 2 s timeout. The 5 s figure in `api/database.py` is a per-query Neo4j timeout, not a request limit (the page waits 10 s, nginx 30 s), so any runtime design must budget the model, readiness, graph queries, fallback and the single worker together.

Passing makes step 4 worth considering; it does not authorise runtime use or show real-world safety. A synthetic set of this size has wide uncertainty.

## Recorded with every run

Requested and returned model ids and any exposed digest (a cloud digest does not prove fixed hosted weights), the Ollama version, UTC timestamps, the SHA-256 of the set, dictionary, prompt and validator, and the generation and thinking settings. Temperature 0 and a fixed seed are requested, not guaranteed. Per-case frames and timings stay local and git-ignored; reasoning traces and free text are not kept.

## Results

### Rules (baseline)

Scored 2026-10-26 04:28 UTC at commit `38e2b22255ac`; set SHA-256 `33c6ac5e8a284a0e…`, 150 scenarios. Turns are counted, not scenarios; held-out turns only unless marked dev.

| Measure | Isolated turns | Full conversations |
|---|---|---|
| Complete frames, held out | 124/180 (68.9%) | 124/180 (68.9%) |
| Complete frames, paraphrase and multi-turn | 42/75 (56.0%) | 42/75 (56.0%) |
| Complete frames, safety subset | 63/85 (74.1%) | 63/85 (74.1%) |
| Complete frames, dev | 28/43 (65.1%) | 28/43 (65.1%) |
| Wrong-subject (unsafe) answers, held out | 12 | 12 |

| Category (held out) | Isolated correct | Isolated unsafe | Conversations correct | Conversations unsafe |
|---|---|---|---|---|
| paraphrase | 23/42 (54.8%) | 0 | 23/42 (54.8%) | 0 |
| multi_turn | 19/33 (57.6%) | 0 | 19/33 (57.6%) | 0 |
| subject_change | 15/16 (93.8%) | 0 | 15/16 (93.8%) | 0 |
| unknown_subject | 10/11 (90.9%) | 0 | 10/11 (90.9%) | 0 |
| negation | 2/10 (20.0%) | 4 | 2/10 (20.0%) | 4 |
| alias | 6/7 (85.7%) | 0 | 6/7 (85.7%) | 0 |
| type_ambiguity | 4/5 (80.0%) | 0 | 4/5 (80.0%) | 0 |
| selection | 7/10 (70.0%) | 0 | 7/10 (70.0%) | 0 |
| mixed_unsupported | 4/5 (80.0%) | 1 | 4/5 (80.0%) | 1 |
| unsupported | 5/9 (55.6%) | 4 | 5/9 (55.6%) | 4 |
| injection | 7/10 (70.0%) | 3 | 7/10 (70.0%) | 3 |
| typo | 10/10 (100.0%) | 0 | 10/10 (100.0%) | 0 |
| reset | 12/12 (100.0%) | 0 | 12/12 (100.0%) | 0 |
