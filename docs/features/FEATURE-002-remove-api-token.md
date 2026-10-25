# FEATURE-002: Remove the API token

**Goal.** Users ask questions without pasting a token; the API stays protected against floods (D-013).

**Scope.** Backend (`api/main.py`), frontend (token field, `Authorization` header), Docker (`compose.yaml`, nginx rate limit), smoke test, `.env.example`, README and `docs/`.

**Design.** The token check and `CHATBOT_API_TOKEN` are removed. CORS no longer allows the `Authorization` header. In Docker, nginx limits each client to 10 requests per second with a burst of 20 and answers 429 beyond that; the page shows "Too many questions at once". The dev server and the Compose stack still listen on 127.0.0.1 only.

**Status.** Done on branch `feat/remove-api-token`.

**Open questions.** None; hosting publicly would reopen D-013.

## Log

- 2026-10-25: Owner chose removal over an optional token. Backend 120 tests passed, frontend 8 helper and 11 component tests passed, Compose smoke test passed including the new 429 check.
