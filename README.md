# Medical-ChatBot

This is a student prototype for local use. It is not medical advice and is not built for public deployment.

Mr. Healthcare answers basic questions about 658 diseases and their symptoms (symptoms, causes, prevention, treatments, complications, descriptions) from a Neo4j knowledge graph, and says plainly when it cannot answer. A Vue 3 page talks to a Flask API. The API finds disease and symptom names with an Aho-Corasick automaton and answers only through fixed, parameterized Cypher queries. A language model (`gpt-oss:120b-cloud` through a local Ollama) may read each question to understand it better, but it only chooses among the names the rules found and never writes an answer; when it is unavailable, slow or unsure, the rules answer. Long answers are shown with their own headings and numbered points, and more conversational rewordings are served only after the owner approves each one against the original.

## Setup

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

Run the checks with `python -m pytest tests` from the repository root, and `yarn lint` and `yarn test` from `frontend/` (`yarn test` runs the Node helper tests and the Vitest component tests). None of them needs a running Neo4j server. GitHub Actions runs them when the files they cover change (see CI/CD and MLOps).

The live tests in `tests/test_live_neo4j.py` run against a real server and **delete all data in it**, so they only run when `NEO4J_TEST_URI`, `NEO4J_PASSWORD` and `NEO4J_TEST_ALLOW_WIPE=1` are set. Use a disposable container, for example `docker run --rm -p 127.0.0.1:7687:7687 -e NEO4J_AUTH=neo4j/<test password> neo4j:5`. CI runs them against Neo4j 5 and 4.4.

## Docker

`compose.yaml` runs Neo4j, the API (gunicorn, one worker) and the web frontend (nginx), reading `NEO4J_PASSWORD` from `.env`. Only the web port is published, on `127.0.0.1:8080` (`WEB_PORT` changes it); nginx serves the page and forwards `/api/` to the API, so the browser talks to one origin and no CORS setup is needed. Neo4j is reachable only inside the stack.

```
docker compose up -d --wait neo4j
docker compose --profile init run --rm importer   # first run, or after the data changes
docker compose up -d
```

The importer replaces the graph snapshot, so it runs only when asked for; a normal `up` or restart never re-imports. An existing graph picks up importer fixes only when you re-run the importer, so back up the `neo4j-data` volume first. The graph lives in the `neo4j-data` volume and the API logs in `api-logs`. Back up the graph by stopping the stack and copying the `neo4j-data` volume; to roll back, restore the volume, or run the importer from the image of the release you want. Restart `api` after an import so it loads the new dictionary. To run a published release instead of building locally, set `API_IMAGE` and `WEB_IMAGE` to the values in that release's `release.env`.

nginx writes no access or error log, because both would contain the question from the request URL. The cost is that nginx problems are not logged; to debug locally, temporarily set `error_log stderr warn;` in `docker/nginx.conf`, and never publish that image. The API container's healthcheck calls `GET /health` (also reachable as `/api/health`), which answers 200 `{"status": "ok"}` only while the graph holds the dictionary's diseases from the same CSV, and 503 `{"status": "unavailable"}` otherwise, for example before the first import. Questions run the same check: while the graph does not match the dictionary the API was started with (a missing, older or different import), `/` answers 503 "The knowledge graph is unavailable" instead of answering from the wrong graph. After an import, restart the API.

**Automatic updates.** `scripts/update_stack.py` updates the running stack when a new release is published. Every 15 minutes it checks the latest release; if it is newer, it pulls the images, stops the stack for about a minute, backs up the graph volume to `deploy/backups/`, re-imports the graph with the new image, starts the new release and checks that it answers. If anything fails, it restores the previous release and backup and does not try that release again. It never starts a stack you stopped, and it only runs while you are signed in with Docker Desktop running.

Set it up once:

1. Run a published release: download its `compose.yaml` and `release.env` from the GitHub release, then `docker compose -f <that compose.yaml> --project-directory . up -d` with `API_IMAGE` and `WEB_IMAGE` set from `release.env`.
2. Record it: `.venv\Scripts\python scripts\update_stack.py --enroll`. It checks that the running images and `compose.yaml` are that release's, and changes nothing.
3. Schedule it from PowerShell: `schtasks --% /Create /TN "Medical-ChatBot update" /SC MINUTE /MO 15 /IT /F /TR "<repo>\.venv\Scripts\pythonw.exe <repo>\scripts\update_stack.py"`, with `<repo>` the full path of this folder. `--%` stops PowerShell from rewriting the quotes; if the path contains spaces, use `Register-ScheduledTask` instead. Check it with `schtasks /Query /TN "Medical-ChatBot update" /V /FO LIST`.

A release that changes `compose.yaml` is not deployed automatically: review it, deploy it by hand as in step 1, and enrol again. While the task is enabled, run `python scripts/update_stack.py` instead of pulling or restarting the stack by hand. Logs go to `logs/<year>/<Month>/update_stack.log`; recovery steps are in `docs/ROLLBACK.md`.

`scripts/compose_smoke.sh` builds both images and tests the whole stack in a throwaway project: import, the page, an answer through `/api`, an abstention, rate limiting, an API outage, and that no question reaches any container output or API log file.

## CI/CD and MLOps

Every workflow runs only when its inputs change, so documentation-only changes start nothing. Nothing is published until `autorelease.yml` or the owner starts a release.

| Workflow                 | Runs when these change                                                                                                                                                | What it does                                                                                                      |
|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| `backend.yml`            | `api/`, `tests/`, `notebooks/`, `eval/`, `scripts/evaluate_kg.py`, `scripts/next_release.py`, the release workflows, `requirements*.txt`                              | Offline pytest suite                                                                                              |
| `frontend.yml`           | `frontend/`                                                                                                                                                           | Lint, tests and build on Node 22 and 24                                                                           |
| `mlops.yml`              | the CSV, the dictionary, the importer and the modules that answer questions, `eval/`, the evaluator, the requirements and the importer, evaluation and live tests     | Data gates, live tests on Neo4j 5 and 4.4, then a real import and evaluation on Neo4j 5                           |
| `docker.yml`             | `docker/`, `compose.yaml`, the requirements, the smoke script, and the `api/` and `frontend/` files copied into the images                                            | Builds both images and runs the Compose smoke test                                                                |
| `release.yml`            | a pushed `vX.Y.Z` tag, a manual run, or a call from `autorelease.yml`                                                                                                 | Continuous delivery (below)                                                                                       |
| `autorelease.yml`        | `automerge` finishes, a manual run, or its own previous successful run                                                                                                | Releases the oldest merge not yet released, with its version, through `release.yml`, then starts the next run     |
| `mirror.yml`             | `release.yml` after publishing, or a manual run with a tag                                                                                                            | Copies the release's images to Docker Hub by digest                                                               |
| `dockerhub-metadata.yml` | `automerge` finishes, or a manual run                                                                                                                                 | Makes the Docker Hub pages match `docs/dockerhub/`                                                                |
| `workflows.yml`          | `.github/workflows/`                                                                                                                                                  | Lints every workflow with actionlint                                                                              |
| `automerge.yml`          | a CI workflow finishes, or a pull request is opened or updated                                                                                                        | Merges the pull request into `main` once every check on its latest commit has passed                              |

**Automatic merging.** A pull request from a branch of this repository is merged into `main` as soon as every check on its latest commit has passed, with no review. If a check fails, the pull request stays open; push a fix and it merges when the checks pass. A pull request whose changes start no CI (documentation only) is merged about a minute after it is opened. Pull requests from forks and drafts are never merged automatically. The merge is made with the workflow's own token, so it does not start the `main` runs of the other workflows again; the pull request's runs already tested the change.

Superseded pull-request runs are cancelled; runs on `main` and releases are not. Each workflow can also be started by hand from the Actions tab. `main` has no branch protection, so a workflow skipped by its path filter blocks nothing. Before requiring status checks, add one always-running gate job, or skipped checks will stay pending forever.

**MLOps.** The runtime serves a knowledge graph, not a trained model, so the pipeline manages the graph's lifecycle. The importer refuses a CSV with missing columns, rows without a disease name, or no diseases left after quarantine. `scripts/evaluate_kg.py` imports the shipped CSV into a disposable Neo4j and runs the reviewed cases in `eval/cases.jsonl` through the real chatbot: intents, entities, mandatory abstentions, and expected facts that tests trace back to the CSV records. It fails if any case fails, or if the import counts differ from the reviewed `eval/baseline.json`. It also checks the integrity of the imported graph, independently of the importer: the importer's nodes, relationships and properties (values and types) must match what the CSV produces exactly, with no self-loops, department cycles, orphaned symptoms or departments, missing uniqueness constraints, or relationships crossing into data the importer does not own, and the entity dictionary must match the graph. Unrelated data in the same database is counted but allowed. Change the baseline or the cases only in a reviewed commit; CI never rewrites them. The report (`eval-report.json`, also shown in the run summary) holds counts, case IDs, the source hash, the commit and the Neo4j version, never a question or an answer. This checks that answers match the source data; it does not measure medical accuracy.

**Releasing.** Every merge that changes files shipped in the images or the release (`api/`, `frontend/`, `docker/`, `compose.yaml`, the runtime requirements and `.env.example`; not docs, tests, evaluation cases or workflows) gets its own release, in merge order. After `automerge` finishes, `autorelease.yml` releases the oldest merge not yet released and, if that succeeds, starts itself again for the next one. The version is the next patch, or minor or major when that merge's pull request carries the `release:minor` or `release:major` label, or when chosen with the `bump` input of a manual run. A failed release stops the chain, and later merges wait until it is fixed. It stops, and tells you what to do, if the last release was left incomplete (see `docs/ROLLBACK.md`). A version can also be released by hand: push a tag such as `v1.0.0` from a commit on `main`, or run `release.yml` with `tag` and `sha`. The release workflow checks that the tag is stable SemVer, is on `main`, and has no existing release or images. It then runs the backend, frontend and MLOps checks on that exact commit, and builds and pushes both images to GHCR under `sha-<commit>-<run>-<attempt>` with an SBOM and provenance, so a retry never overwrites an earlier push. It smoke-tests those exact image digests with Compose, and then drafts a GitHub Release. The release holds `compose.yaml`, `env.example`, `release.env` (the image digests), the frontend build, `entities.json`, the evaluation report and a manifest. A new version's git tag is created only at this point, after every check has passed. Only after every asset uploads does it add the version tag to the images and publish the release. There is no `latest` tag, and published versions are never overwritten. New GHCR packages are private even in a public repository; to allow anonymous pulls, change each package's visibility under the repository's Packages settings.

**Docker Hub.** Each release is also copied, byte for byte, to Docker Hub under the same version, with no `latest`: `docker pull hamzaazizai/medical-chatbot-api:1.1.13` (and `-web`). GHCR stays the source: `release.env`, compose and the updater use GHCR digests. The copy is a separate run, so a Docker Hub problem shows as a failed `mirror` run and never blocks a release; re-run `mirror.yml` with the tag (D-030). The Docker Hub descriptions and overview come from `docs/dockerhub/` and are synced after every merge, version tags there are immutable, and the images carry OCI labels linking them to this repository (D-031).

**Hosting.** The owner's public site runs on an Oracle Cloud Always Free VM, with the graph on Neo4j AuraDB Free and HTTPS through a Cloudflare Tunnel; no application port is open, the language model is off, and the VM updates itself from each release, closing public access while the graph is rebuilt (D-032). [hosting/oracle/README.md](hosting/oracle/README.md) sets it up.

**Not automated.** Retraining the historical notebooks is not automated either, because they are not used at runtime, cannot be reproduced (see Known limitations), and need Kaggle access and the multi-gigabyte GloVe embeddings. There are no scheduled runs.

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

The API does not log questions, tokens or credentials, and silences the development server's request log, which would otherwise print each question in the URL. This applies to the Flask app and its local development server. The Docker images keep the same rule: gunicorn has no access log, and nginx logs nothing (see Docker). Configure any other server or proxy separately.

## Runtime behavior

The API answers supported questions from the Neo4j knowledge graph. It returns an explicit abstention when no graph answer is available or a question requests treatment duration, cure probability or susceptibility. Questions combining supported and unsupported intents also abstain. Intents are detected from whole words and phrases (for example "cause", "symptoms", "how long"), so classification is still limited: a supported question phrased with words outside these lists gets a description or an abstention instead.

The API accepts `GET /?search=<question>` and `GET /health` only; other methods return a JSON 405 error. The reply is JSON with `message` (the plain answer) plus `status` (answer, clarify or abstain), `reason`, `answers` (list answers carry `lead`, `items` and `note`), `topic`, `interpretation` and `options` (suggested or clarifying questions). The page sends back the confirmed `topic` and `topic_type` so follow-ups such as "what causes it?" work, and `selection=<name>:<type>` for choices made while clarifying. Neither is stored or logged. Suggestions come from the answerable intents the importer writes into `entities.json`, so they never need a database query. Other names listed in `api/dictionary/aliases.json` (each sourced from a MedlinePlus "Also called" list) are understood, such as "whooping cough" for pertussis. A misspelled name gets "Did you mean ...?" choices; the bot never applies a correction on its own.

With `LLM_UNDERSTANDING=on` (the Docker default; off unless set when running Flask directly), a language model reads each question first (D-027): `gpt-oss:120b-cloud` through your local Ollama (`OLLAMA_URL`, `LLM_MODEL`), which must be installed and signed in. It only chooses among the disease and symptom names found in the question and the allowed question types; answers still come only from the graph, and on any failure, timeout or busy budget the rules answer as before. Questions and relevant topic context may be sent to Ollama's cloud to understand them; answers come only from the knowledge graph. Set `LLM_UNDERSTANDING=off` to keep questions on this machine.

Long text answers keep every word but show their own headings and numbered points (`sections`, D-028). A reworded, more conversational version is added beside the original only when the owner has approved that exact field (`reworded_sections`, D-029); the store `api/dictionary/rewordings.json` ships empty. Every API response carries `Cache-Control: no-store`, because the question travels in the URL. With the model on, `understanding.log` holds outcome counts (attempts, routed, failures, budget denials), never questions or addresses.

The API does not load similarity models or return stored patient answers. No model weights or Quora training download are required for the API.

## Language-model evaluation and rewording (offline)

These scripts call the cloud model through your local Ollama; they never run in CI and never touch the running API.

```
python scripts/llm_understanding.py --round2 --dry-run   # check the frozen Round-2 inputs; no model calls
python scripts/reword_answers.py --inventory             # sizes of the rewording pilot fields; no model calls
python scripts/reword_answers.py --challenge             # measure the rewording checks on reviewed broken rewrites
python scripts/reword_answers.py --generate              # reword the pilot fields into local candidates
python scripts/reword_answers.py --review                # write pilot-data/rewordings/review.html for the owner
python scripts/reword_answers.py --approve decisions.json   # publish only approved, unchanged, passing fields
```

Results: [docs/pilot/LLM-UNDERSTANDING.md](docs/pilot/LLM-UNDERSTANDING.md) (Rounds 1 and 2) and [docs/pilot/REWORDING.md](docs/pilot/REWORDING.md).

## Historical training experiments

The notebooks and model assets remain historical experiments. Their dependencies, including Keras and TensorFlow, are not supplied by the runtime requirements; use a separate environment.

The training notebooks expect the Quora Question Pairs data at `notebooks/data/train.csv`. It is not committed; download it from Kaggle (requires a Kaggle API token and accepting the competition rules):

```
kaggle competitions download -c quora-question-pairs -p notebooks/data
```

Unzip the download so that `notebooks/data/train.csv` exists.

## Project documentation

The `docs/` folder follows the "Defend What You Ship" field guide. Start with [docs/HANDOVER.md](docs/HANDOVER.md) (where things stand) and [docs/CONSTRAINTS.md](docs/CONSTRAINTS.md) (rules for changes). It also holds the decision log, rejected alternatives, architecture, request flow, threat and failure maps, data structures, test checklist, rollback plan, open assumptions, dependency and secrets log, and a one-page defense brief.

## Known limitations

- **Training reproducibility.** The notebook fits its tokenizer before splitting the data, does not seed the split, and has no separate test set. Fixing this needs the training data, the GloVe embeddings and a new evaluation run, so it has not been done.
- **Language model.** It runs by the owner's decision before meeting its pre-registered bar: on a fresh set it understood far more phrasings and added no wrong-subject answer the rules do not also give, but missed the reliability (98.1% usable replies) and latency (p95 1.56 s) targets. Real questions go to Ollama's cloud while it is on; set `LLM_UNDERSTANDING=off` to keep them on this machine.
- **Access control.** The API has no authentication (D-013 in `docs/DECISIONS.md`). It answers read-only questions over public data and listens on this machine only; in Docker, nginx limits each client to 10 questions per second. Putting it on the internet would need real authentication and HTTPS first.
