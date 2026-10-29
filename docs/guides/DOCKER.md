# Docker

Running the whole stack on one machine with Docker Compose, and keeping it updated. Back to the [README](../../README.md).

`compose.yaml` runs Neo4j, the API (gunicorn, one worker) and the web frontend (nginx), reading `NEO4J_PASSWORD` from `.env`. Only the web port is published, on `127.0.0.1:8080` (`WEB_PORT` changes it); nginx serves the page and forwards `/api/` to the API, so the browser talks to one origin and no CORS setup is needed. Neo4j is reachable only inside the stack.

```
docker compose up -d --wait neo4j
docker compose --profile init run --rm importer   # first run, or after the data changes
docker compose up -d
```

The importer replaces the graph snapshot, so it runs only when asked for; a normal `up` or restart never re-imports. An existing graph picks up importer fixes only when you re-run the importer, so back up the `neo4j-data` volume first. The graph lives in the `neo4j-data` volume and the API logs in `api-logs`. Back up the graph by stopping the stack and copying the `neo4j-data` volume; to roll back, restore the volume, or run the importer from the image of the release you want. Restart `api` after an import so it loads the new dictionary. To run a published release instead of building locally, set `API_IMAGE` and `WEB_IMAGE` to the values in that release's `release.env`.

nginx serves the page itself (`/` and `/index.html`) with `Cache-Control: no-cache`, so every load gets the current release (D-037); the hashed assets keep nginx's defaults. nginx writes no access or error log, because both would contain the question from the request URL. The cost is that nginx problems are not logged; to debug locally, temporarily set `error_log stderr warn;` in `docker/nginx.conf`, and never publish that image. The API container's healthcheck calls `GET /health` (also reachable as `/api/health`), which answers 200 `{"status": "ok"}` only while the graph holds the dictionary's diseases from the same CSV, and 503 `{"status": "unavailable"}` otherwise, for example before the first import. Questions run the same check: while the graph does not match the dictionary the API was started with (a missing, older or different import), `/` answers 503 "The knowledge graph is unavailable" instead of answering from the wrong graph. After an import, restart the API.

**Automatic updates.** `scripts/update_stack.py` updates the running stack when a new release is published. Every 15 minutes it checks the latest release; if it is newer, it pulls the images, stops the stack for about a minute, backs up the graph volume to `deploy/backups/`, re-imports the graph with the new image, starts the new release and checks that it answers. If anything fails, it restores the previous release and backup and does not try that release again. It never starts a stack you stopped, and it only runs while you are signed in with Docker Desktop running.

Set it up once:

1. Run a published release: download its `compose.yaml` and `release.env` from the GitHub release, then `docker compose -f <that compose.yaml> --project-directory . up -d` with `API_IMAGE` and `WEB_IMAGE` set from `release.env`.
2. Record it: `.venv\Scripts\python scripts\update_stack.py --enroll`. It checks that the running images and `compose.yaml` are that release's, and changes nothing.
3. Schedule it from PowerShell: `schtasks --% /Create /TN "Medical-ChatBot update" /SC MINUTE /MO 15 /IT /F /TR "<repo>\.venv\Scripts\pythonw.exe <repo>\scripts\update_stack.py"`, with `<repo>` the full path of this folder. `--%` stops PowerShell from rewriting the quotes; if the path contains spaces, use `Register-ScheduledTask` instead. Check it with `schtasks /Query /TN "Medical-ChatBot update" /V /FO LIST`.

A release that changes `compose.yaml` is not deployed automatically: review it, deploy it by hand as in step 1, and enrol again. While the task is enabled, run `python scripts/update_stack.py` instead of pulling or restarting the stack by hand. Logs go to `logs/<year>/<Month>/update_stack.log`; recovery steps are in `docs/ROLLBACK.md`.

`scripts/compose_smoke.sh` builds both images and tests the whole stack in a throwaway project: import, the page, an answer through `/api`, an abstention, rate limiting, an API outage, and that no question reaches any container output or API log file.
