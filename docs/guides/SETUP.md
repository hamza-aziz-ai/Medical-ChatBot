# Local setup

Running the API and the page from source, without Docker, and what the importer and the logs do. Back to the [README](../../README.md).

## Install and run

Tested with Python 3.14. The importer and API were tested live against the official Docker images Neo4j 5.26.32 and 4.4.48; other Neo4j versions are untested.

```
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip
```

Configuration comes from environment variables. For local use, copy `.env.example` to `.env` in the repository root and fill it in; the API and the importer read it at startup, and variables already set in your shell take precedence. `.env` is git-ignored, so keep real secrets only there.

| Variable                  | Required     | Default                                                                                                                                  |
|---------------------------|--------------|------------------------------------------------------------------------------------------------------------------------------------------|
| `NEO4J_PASSWORD`          | yes          | none                                                                                                                                     |
| `NEO4J_URI`               | no           | `neo4j://localhost:7687` (Bolt schemes only: `bolt`, `neo4j` and their `+s`/`+ssc` variants; query timeouts do not work over HTTP)       |
| `NEO4J_USER`              | no           | `neo4j`                                                                                                                                  |
| `NEO4J_DATABASE`          | no           | `neo4j`                                                                                                                                  |
| `NEO4J_QUERY_TIMEOUT`     | no           | `5` (seconds per API query; must be a positive number)                                                                                   |
| `CORS_ORIGINS`            | no           | `http://localhost:8080,http://127.0.0.1:8080` (exact `http(s)://host[:port]` origins, comma-separated; patterns and `*` are refused)     |

An earlier version of this repository contained a hard-coded Neo4j password. If you used that password anywhere, change it.

Build the graph, then start the API (it listens on 127.0.0.1 only):

```
cd api
python build_medicalgraph.py
flask --app main run
```

The frontend is Vue 3 built with Vite and needs Node `^22.13.0 || ^24.0.0`. From `frontend/`, run `yarn install` and then `yarn dev` (development, http://localhost:8080) or `yarn build` and `yarn preview` (the built site on the same port, which the API's default CORS origins allow). Set `VITE_API_BASE_URL` in `frontend/.env` (template: `frontend/.env.example`) if the API is not at `http://localhost:5000`. Never put a secret in a `VITE_*` variable: Vite compiles those into the public bundle. The page needs no login or token.

Run the checks with `python -m pytest tests` from the repository root, and `yarn lint` and `yarn test` from `frontend/` (`yarn test` runs the Node helper tests and the Vitest component tests). None of them needs a running Neo4j server. GitHub Actions runs them when the files they cover change (see [CI/CD and MLOps](CI-CD.md)).

The live tests in `tests/test_live_neo4j.py` run against a real server and **delete all data in it**, so they only run when `NEO4J_TEST_URI`, `NEO4J_PASSWORD` and `NEO4J_TEST_ALLOW_WIPE=1` are set. Use a disposable container, for example `docker run --rm -p 127.0.0.1:7687:7687 -e NEO4J_AUTH=neo4j/<test password> neo4j:5`. CI runs them against Neo4j 5 and 4.4.

## Graph import

`api/build_medicalgraph.py` validates `api/data/medical.csv` before writing anything. It never modifies the CSV.

- A list cell that is not a valid Python list of strings is excluded for that disease only; the rest of the record is imported. The import reports each excluded field with its row and column.
- When the same disease name appears with conflicting records, every version is excluded from the import and reported. Identical duplicates are merged.
- Empty, punctuation-only and known artefact terms (such as "living") are dropped.
- Accompanying conditions that do not match an imported disease are reported, not created. A disease listed as its own complication is reported and gets no link.
- A Cure Department list names either one department or a `[parent, child]` pair. A repeated department such as `['oncology', 'oncology']` counts as one department and creates no hierarchy link. A list naming more than two departments is excluded for that disease, like any other invalid list cell. A department hierarchy that loops back on itself stops the import before anything is written.
- Every node and relationship the importer writes is marked as its own. A re-import replaces that marked snapshot completely, so facts and diseases removed from the CSV disappear from the graph. Nothing unmarked is ever changed or deleted.
- The import refuses to run if an unmarked node has the name of a node it would write (including excluded disease names), or if an unmarked relationship touches one of its nodes. Reconcile those records manually or use a fresh database.
- Uniqueness constraints are created first. All graph data is then written in one transaction (120 s limit), so a failure commits no data, although the constraints remain. The entity dictionary `api/dictionary/entities.json` is staged first and replaced in one step only after the graph commits. If that last step fails, the import exits with an error and the previous dictionary stays; re-run the import. Restart a running API to load a new dictionary.

## Data provenance

The source and clinical review status of `medical.csv` are unknown. Each imported disease records `source_file`, `source_sha256`, `source_rows` and `clinical_review="unverified"`. These record where the data came from locally; they are not evidence of clinical accuracy.

## Logging

Every backend module writes its own rotating log file in `logs/<year>/<Month>/`, named after the module: `main.log`, `chatbot_graph_logic.log`, `question_classifier.log`, `question_parser.log`, `answer_searcher.log`, `database.log`, `terms.log`, `build_medicalgraph.log` and `app_logging.log`. Messages from third-party libraries go to `external.log`. The frontend runs in the browser and does not write log files. If the API and the importer run at the same time, the modules they share (`database`, `terms`) write to the same file, and its midnight rotation can fail while the other process holds it open. Each file is closed at midnight and renamed `<name>.log.DD-MMM-YYYY` (for example `api.log.25-Oct-2026`) in the folder it was written in, and a new file starts in the folder for the current month. Lines look like `25 October 2026, Sunday, 02:15:53.293 PM India Standard Time [INFO] main: Answered a question of 18 characters`. The timezone is the operating system's local name: an abbreviation such as `IST` on Linux and macOS, the full name on Windows.

| Variable               | Default                           | Meaning                                                                         |
|------------------------|-----------------------------------|---------------------------------------------------------------------------------|
| `LOG_LEVEL`            | `DEBUG`                           | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`                               |
| `LOG_BACKUP_COUNT`     | `30`                              | Rotated files kept per module log, across all folders; `0` keeps every file     |
| `LOG_DIR`              | `logs` in the repository root     | Where the year folders go; git-ignored                                          |

The API does not log questions, tokens or credentials, and silences the development server's request log, which would otherwise print each question in the URL. This applies to the Flask app and its local development server. The Docker images keep the same rule: gunicorn has no access log, and nginx logs nothing (see [Docker](DOCKER.md)). Configure any other server or proxy separately.
