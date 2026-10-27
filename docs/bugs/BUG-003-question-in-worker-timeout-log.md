# BUG-003: A question reaches the container log when a worker times out

**Symptom.** When a request stalls long enough for Gunicorn's watchdog to kill the worker, the API container's output contains the full request line, question included.

**Repro.** Run the v1.1.13 API image with `NEO4J_URI` pointing at a listener that accepts and never answers, and `GUNICORN_CMD_ARGS="--timeout 3"`. Ask any question: `docker logs` shows `[ERROR] Error handling request GET /?search=what+causes+asthma+...` right after `[CRITICAL] WORKER TIMEOUT`.

**Root cause.** Gunicorn 26.2.0's sync worker catches the abort raised in a killed worker and logs it through `handle_error()` with the request URI, at error level, to stderr. The API's own logging never records questions, but Gunicorn's error log was left at its default level. The smoke test checked every log, yet never forced a timeout, so the path was never exercised.

**Fix.** The API image runs Gunicorn with `--log-level critical`. The URI-bearing message is error level and is dropped; `WORKER TIMEOUT (pid:…)` is critical, carries no URI, and stays. Boot failures still show as the container exiting and failing its healthcheck, and application errors go through `app_logging`, which never logs questions.

**Verification.** `scripts/compose_smoke.sh` points a separate API container at a stalling listener, asks a question with a sentinel, requires the `WORKER TIMEOUT` line (the path ran), and fails if the sentinel appears in the container output or the API's log files. It passed locally with the fix; the same steps on the v1.1.13 image show the question in the log.

## Log

- 2026-10-27: Found by Codex during the hosting design council (D-032); reproduced on v1.1.13 and fixed.
