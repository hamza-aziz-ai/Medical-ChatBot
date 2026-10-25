# FEATURE-008: Readiness route

**Goal.** Report whether the graph is really loaded, for Docker and the stack updater (D-022).

**Scope.** `api/main.py` (`GET /health`), `api/chatbot_graph_logic.py` (`ready`, `load_source`), `api/answer_searcher.py` (`readiness`), `docker/api.Dockerfile` (healthcheck), `.github/workflows/release.yml` (manifest `capabilities.health`), `scripts/update_stack.py`, `scripts/compose_smoke.sh`, tests and docs.

**Design.** One non-retrying READ counts importer-owned diseases and those stamped with the dictionary's CSV hash; ready only when both equal the dictionary's disease count. The body says only ok or unavailable. The updater checks the route only for releases whose manifest declares it.

**Status.** Built on branch `feat/health-route`.

**Open questions.** None.

## Log

- 2026-10-26: Built after a council with Codex. Offline 269 passed, 9 skipped; live 279 passed; evaluation 22/22; Compose smoke test passed, including a Neo4j outage with the API running (503, then 200).
