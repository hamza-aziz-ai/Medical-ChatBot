# FEATURE-012: Long answers as sections and numbered points

**Goal.** Make long graph answers readable without changing their words (D-028).

**Scope.** `api/text_format.py`, `api/answer_searcher.py` (`structure`), `api/app_logging.py`, the chat panel and its styles, tests.

**Design.** See D-028.

**Status.** Built; the language-model rewording step comes next and is designed separately.

## Log

- 2026-10-26: Built. Asthma prevention now shows "Daily asthma prevention" (4 points) and "Health education" (6 points); 464 stored fields are structured, all with their letters intact in order.
