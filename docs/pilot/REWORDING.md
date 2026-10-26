# Rewording pilot (D-029)

Reworded, more conversational versions of three prose answers (description, causes, prevention), generated offline by `scripts/reword_answers.py` and shown to users only after the owner approves each field side by side. This page holds aggregates only; per-field candidates and the review page stay in git-ignored `pilot-data/rewordings/`. Design agreed with Codex in council (D-029 and its addendum).

## How a field gets served

1. `prose_segments()` splits the field the same way the API does; each paragraph or numbered point is reworded on its own, with the whole field as context, by `gpt-oss:120b-cloud` (30 s offline deadline).
2. Filters per passage: numbers, units and negation words kept; no new names the dictionary recognises; length within 0.5 to 1.6 times. Then a verifier call on the whole field: additions, omissions, contradictions, reversed causes, certainty and quantity changes. The verifier is the same model, so this is correlated checking, not an independent second opinion.
3. The owner reviews every field and approves it by its exact input, output and formatter identities. `--approve` publishes only fields that passed every check and have not changed since review, into `api/dictionary/rewordings.json`.
4. The API serves an entry only when its input, output and formatter identities all still match, next to the untouched original, with "Show original". The store ships empty.

## Challenge set

Measured 2026-10-26 11:44 UTC: 45 reviewed cases in `eval/rewording-challenges.jsonl`, 45 verifier calls to `gpt-oss:120b-cloud`. A mutation is caught when a check flags it; a faithful control is wrongly rejected when a check flags it. The verifier is the same model as the writer, so its catches are correlated with the writer's blind spots. Checks are filters, not proof.

| Case kind | Cases | Mechanical filters flag | Verifier flags | Either flags |
|---|---|---|---|---|
| added_fact | 6 | 3/6 | 6/6 | 6/6 |
| cause_reversal | 4 | 0/4 | 4/4 | 4/4 |
| certainty_change | 6 | 0/6 | 6/6 | 6/6 |
| control | 10 | 3/10 | 0/10 | 3/10 |
| dropped_clause | 6 | 0/6 | 6/6 | 6/6 |
| negation_flip | 6 | 6/6 | 6/6 | 6/6 |
| quantity_change | 5 | 4/5 | 5/5 | 5/5 |
| quantity_swap | 2 | 0/2 | 2/2 | 2/2 |

Findings: the verifier flagged every mutation and none of the faithful controls; the mechanical filters caught negation flips and most digit changes but missed reversed causes, swapped quantities, dropped clauses and certainty changes, and wrongly flagged 3 of 10 faithful controls ("has not been determined" adds a "not"; "people with obesity" and "sleeping" introduce dictionary names). Number words such as "four or five" are not checked. 45 cases is small; these rates are indicative only.

## Pilot generation

Generated 2026-10-26 for the ten fields agreed before generation, in 54 cloud calls (44 passages and 10 field checks). Two fields passed every check (migraine description, pertussis prevention); eight were flagged. Across the 44 passages the filters flagged negation counts 9 times, new dictionary names 9 times, numbers 2, units 2 and length 1; the verifier flagged three fields (a changed quantity in gout prevention; an omission and a contradiction in migraine causes). Flagged fields cannot be approved. Nothing is served until the owner approves fields in the review page.

## Cloud calls

Rewording used 99 calls (45 challenge checks and 54 for the pilot). With Round 2's 752, the session used 851 of the owner's allowance of roughly 1,000 to 1,500.
