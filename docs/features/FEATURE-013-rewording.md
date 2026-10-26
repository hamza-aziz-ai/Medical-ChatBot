# FEATURE-013: Reworded prose answers, approved by the owner

**Goal.** Make long answers more conversational without letting a model change a fact unseen (D-029).

**Scope.** `scripts/reword_answers.py`, `eval/rewording-challenges.jsonl`, `api/text_format.py` (`prose_segments`, `FORMAT_IDENTITY`), `api/answer_searcher.py` (store loading and exact-match serving), `api/dictionary/rewordings.json` (empty), the chat panel's toggle, tests.

**Design.** See D-029 and its build addendum; aggregates in `docs/pilot/REWORDING.md`.

**Status.** Built up to the owner's review: 10 pilot candidates generated (2 pass every check), review page local, store empty.

**Open questions.** Which fields the owner approves; whether the filters' false rejections should be tuned on fresh cases.

## Log

- 2026-10-26: Built. Challenge set: verifier 35/35 mutations caught, 0/10 controls flagged; filters 3/10 controls flagged. Pilot: 10 fields, 54 calls, 2 passed every check.
