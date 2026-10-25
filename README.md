# Medical-ChatBot

This is a student prototype for local use. It is not medical advice and is not built for public deployment.

## Setup

Tested with Python 3.14. The importer and API were tested live against the official Docker images Neo4j 5.26.32 and 4.4.48; other Neo4j versions are untested.

```
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip
```

Configuration comes from environment variables. For local use, copy `.env.example` to `.env` in the repository root and fill it in; the API and the importer read it at startup, and variables already set in your shell take precedence. `.env` is git-ignored, so keep real secrets only there.

| Variable | Required | Default |
|---|---|---|
| `NEO4J_PASSWORD` | yes | none |
| `NEO4J_URI` | no | `neo4j://localhost:7687` (Bolt schemes only: `bolt`, `neo4j` and their `+s`/`+ssc` variants; query timeouts do not work over HTTP) |
| `NEO4J_USER` | no | `neo4j` |
| `NEO4J_DATABASE` | no | `neo4j` |
| `NEO4J_QUERY_TIMEOUT` | no | `5` (seconds per API query; must be a positive number) |
| `CHATBOT_API_TOKEN` | yes, for the API | none |
| `CORS_ORIGINS` | no | `http://localhost:8080,http://127.0.0.1:8080` (exact `http(s)://host[:port]` origins, comma-separated; patterns and `*` are refused) |

An earlier version of this repository contained a hard-coded Neo4j password. If you used that password anywhere, change it.

Build the graph, then start the API (it listens on 127.0.0.1 only):

```
cd api
python build_medicalgraph.py
flask --app main run
```

Start the frontend from `frontend/` with `yarn install` and `yarn serve`, using Node 18 (see Known limitations). Set `VUE_APP_API_BASE_URL` if the API is not at `http://localhost:5000`. Enter the value of `CHATBOT_API_TOKEN` in the "API token" field; the page keeps it in memory only.

Run the checks with `python -m pytest tests` from the repository root and `yarn test` from `frontend/`. Neither needs a running Neo4j server. GitHub Actions runs both on every push and pull request.

The live tests in `tests/test_live_neo4j.py` run against a real server and **delete all data in it**, so they only run when `NEO4J_TEST_URI`, `NEO4J_PASSWORD` and `NEO4J_TEST_ALLOW_WIPE=1` are set. Use a disposable container, for example `docker run --rm -p 127.0.0.1:7687:7687 -e NEO4J_AUTH=neo4j/<test password> neo4j:5`. CI runs them against Neo4j 5 and 4.4.

## Graph import

`api/build_medicalgraph.py` validates `api/data/medical.csv` before writing anything. It never modifies the CSV.

- A list cell that is not a valid Python list of strings is excluded for that disease only; the rest of the record is imported. The import reports each excluded field with its row and column.
- When the same disease name appears with conflicting records, every version is excluded from the import and reported. Identical duplicates are merged.
- Empty, punctuation-only and known artefact terms (such as "living") are dropped.
- Accompanying conditions that do not match an imported disease are reported, not created.
- Every node and relationship the importer writes is marked as its own. A re-import replaces that marked snapshot completely, so facts and diseases removed from the CSV disappear from the graph. Nothing unmarked is ever changed or deleted.
- The import refuses to run if an unmarked node has the name of a node it would write (including excluded disease names), or if an unmarked relationship touches one of its nodes. Reconcile those records manually or use a fresh database.
- Uniqueness constraints are created first. All graph data is then written in one transaction (120 s limit), so a failure commits no data, although the constraints remain. The entity dictionary `api/dictionary/entities.json` is staged first and replaced in one step only after the graph commits. If that last step fails, the import exits with an error and the previous dictionary stays; re-run the import. Restart a running API to load a new dictionary.

## Data provenance

The source and clinical review status of `medical.csv` are unknown. Each imported disease records `source_file`, `source_sha256`, `source_rows` and `clinical_review="unverified"`. These record where the data came from locally; they are not evidence of clinical accuracy.

## Logging

The API does not log questions, tokens or credentials, and silences the development server's request log, which would otherwise print each question in the URL. This applies to the Flask app and its local development server only; configure any other server or proxy separately.

## Runtime behavior

The API answers supported questions from the Neo4j knowledge graph. It returns an explicit abstention when no graph answer is available or a question requests treatment duration, cure probability or susceptibility. Questions combining supported and unsupported intents also abstain. Intents are detected from whole words and phrases (for example "cause", "symptoms", "how long"), so classification is still limited: a supported question phrased with words outside these lists gets a description or an abstention instead.

The API accepts `GET /?search=<question>` only; other methods return a JSON 405 error.

The API does not load similarity models or return stored patient answers. No model weights or Quora training download are required for the API.

## Historical training experiments

The notebooks and model assets remain historical experiments. Their dependencies, including Keras and TensorFlow, are not supplied by the runtime requirements; use a separate environment.

The training notebooks expect the Quora Question Pairs data at `notebooks/data/train.csv`. It is not committed; download it from Kaggle (requires a Kaggle API token and accepting the competition rules):

```
kaggle competitions download -c quora-question-pairs -p notebooks/data
```

Unzip the download so that `notebooks/data/train.csv` exists.

## Known limitations

- **Training reproducibility.** The notebook fits its tokenizer before splitting the data, does not seed the split, and has no separate test set. Fixing this needs the training data, the GloVe embeddings and a new evaluation run, so it has not been done.
- **Vue 2.** The frontend uses Vue 2, which reached end of life on 31 Dec 2023, and the `vue-bot-ui` chat widget, whose tooling is Vue 2 based. Moving to Vue 3 needs coordinated frontend work. The locked Vue CLI 5 toolchain refuses to install on Node 20 or later (`@achrinza/node-ipc` supports Node 8–19), so `package.json` declares Node 18; the build was verified with Node 18.20.8, which is itself past end of life. axios was replaced by the browser `fetch` API, but the remaining Vue and build-tool dependencies still carry known vulnerability alerts until this migration happens.
- **Access control.** The API uses one shared token. It has no user accounts.
