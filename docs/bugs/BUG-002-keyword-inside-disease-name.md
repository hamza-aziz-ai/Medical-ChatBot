# BUG-002: Intent keywords inside disease names

**Symptom.** "What causes deep palm infection?" abstains as an unsupported question.

**Repro.** `QuestionClassifier().classify("what causes deep palm infection")` returns intents `disease_cause` and `disease_easy_get`; the second is unsupported, so the bot abstains.

**Root cause.** Intent keywords are matched against the whole question, including the words of the matched disease name. "infection" is a keyword for "who gets it". Four disease names contain it (for example "deep palm infection", "systemic infections caused by enterovirus").

**Fix.** Not fixed yet. The guided-conversation work suppresses suggestion chips that would misclassify, so the bot never offers such a question itself. The proper fix is to ignore keyword matches inside matched entity spans; it changes classification for every question, so it needs its own decision entry and evaluation cases.

**Verification.** `tests/test_conversation.py::test_every_suggestion_in_the_dictionary_round_trips_to_its_intent` asserts no chip is offered for "deep palm infection".

## Log

- 2026-10-25: Found by Codex during the step-1 design review; logged as A-12.
