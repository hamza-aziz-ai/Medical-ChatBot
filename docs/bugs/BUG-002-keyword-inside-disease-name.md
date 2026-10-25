# BUG-002: Intent keywords inside disease names

**Symptom.** "What causes deep palm infection?" abstains as an unsupported question.

**Repro.** Before the fix, `QuestionClassifier().classify("what causes deep palm infection")` returned intents `disease_cause` and `disease_easy_get`; the second is unsupported, so the bot abstained.

**Root cause.** Intent keywords were matched against the whole question, including the words of the matched disease name. "infection" is a keyword for "who gets it". Three disease names contain it: "deep palm infection", "non-cholesteric infection" and "retroperitoneal infection and abscess". Their suggestion chips were suppressed because they misclassified.

**Fix.** `QuestionClassifier.mask_entities` replaces every matched name or alias with `#` before keyword matching in `classify_with` and `has_intent_keyword` (D-018). A name that is itself a keyword ("phenomenon") stays readable as one. `check_medical` and the mask share one span helper, `entity_spans`.

**Verification.** `tests/test_classifier.py` covers the three diseases, keywords outside the name (including the veto in "does infection cause deep palm infection?"), nested and crossing names, aliases, no bridging and "phenomenon". `tests/test_conversation.py` asserts their chips are offered and round-trip. The evaluation case `keyword-inside-name` answers with a fact from CSV row 658. Offline 178 passed, 9 skipped; live 187 passed; evaluation 22/22 with 0 chip mismatches.

## Log

- 2026-10-25: Found by Codex during the step-1 design review; logged as A-12.
- 2026-10-25: Fixed after a council with Codex (D-018). The earlier "four" names was a miscount: it is three.
