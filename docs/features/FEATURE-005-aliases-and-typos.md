# FEATURE-005: Sourced aliases and confirmed typo suggestions

**Goal.** Understand other names and misspellings without guessing (step 2 of the agreed plan; D-017).

**Scope.** `api/dictionary/aliases.json`, `api/question_classifier.py` (`load_aliases`, alias matching, `close_matches`), `api/chatbot_graph_logic.py` (alias and typo clarifications, aliases in the interpretation), the "Why this answer?" note, tests and evaluation cases.

**Design.** Eight aliases from MedlinePlus "Also called" lists, each pointing at an existing dictionary entry of a stated type; matched like names and shown as "\"whooping cough\" was read as pertussis". An alias naming several entries asks which one. When no entity is found, 1-3-word phrases that are not filler or intent keywords are compared with every disease, symptom and alias name (stdlib `difflib`, cutoff 0.8); up to three are offered as "Did you mean ...?" chips that re-ask the corrected question. Nothing is applied without a click.

**Status.** Built on branch `feat/aliases-typos`.

**Open questions.** The cutoff was tuned on 7 misspellings and 7 unrelated words; widen the reviewed set if suggestions misfire.

## Log

- 2026-10-25: Built. Backend 172 tests offline and 181 live passed; evaluation 21/21 with no integrity failures and 0 chip mismatches; frontend 11 helper and 20 component tests passed.
- 2026-10-25: A-13 fixed (D-017 addendum): names containing filler words or intent keywords are suggested whole, from the window that is the misspelling, with punctuation kept. Offline 249 passed, 9 skipped; live 258 passed. A normal typo question takes about 30 ms; the worst case is unchanged (A-14).
