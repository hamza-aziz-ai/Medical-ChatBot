# FEATURE-004: Guided conversation

**Goal.** A more engaging conversation without a language model (step 1 of the agreed plan; D-015, D-016).

**Scope.** `api/chatbot_graph_logic.py` (`respond`), `answer_searcher.py` (structured results), `question_classifier.py` (`classify_with`), `build_medicalgraph.py` (intents in `entities.json`), `main.py` (topic and selections), `scripts/evaluate_kg.py` (status-based checks, chip check), the frontend chat panel, transport and app, and tests.

**Design.** Structured replies with a status and reason; follow-ups that reuse the confirmed topic only for explicit references or short continuations; clarification when a name is both a disease and a symptom, with choices that accumulate and keep the original question; explained abstentions (unknown term, unsupported question, department, nothing recorded); suggestion chips only for intents the graph can answer and that classify back to themselves; list answers as bullets; "Why this answer?"; a topic bar and "New conversation"; always-visible emergency guidance; an external MedlinePlus link.

**Status.** Built on branch `feat/structured-replies`.

**Open questions.** BUG-002 (keywords inside disease names).

## Log

- 2026-10-25: Design agreed with Codex; its connection dropped before the last point, which the LLM council settled (D-016). Backend 151 tests offline and 160 live passed; MLOps evaluation 19/19 with no integrity failures and 0 chip mismatches over 658 diseases; frontend 11 helper and 20 component tests passed; Compose smoke test passed; checked in a browser against the live stack (answer with bullets, follow-up, clarification, choice, chips, topic bar).
