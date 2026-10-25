# ARCHITECTURE

One-page map. Deeper detail: the README, [FLOW.md](FLOW.md), [DATA.md](DATA.md) and the two architecture pages (Solution Architecture and Software & System Design).

## What it is

A rule-based medical question-answering chatbot. It finds disease and symptom names in a question, works out what is being asked from keywords, and answers from a Neo4j knowledge graph built from `api/data/medical.csv`. If it cannot answer from the graph, it says so instead of guessing. There is no machine-learning model at runtime.

## Modules and what they own

| Module                              | Owns                                                                                                              |
|-------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| `frontend/` (Vue 3, Vite)           | The page: chat panel and About panel. Talks to the API through `src/chatApi.mjs`.                                 |
| `api/main.py`                       | The HTTP boundary: CORS, input limits, JSON errors, request logging without questions. No authentication (D-013). |
| `api/chatbot_graph_logic.py`        | One question in, one answer or abstention out.                                                                    |
| `api/question_classifier.py`        | Entity matching (Aho-Corasick over `api/dictionary/entities.json`) and keyword intents.                           |
| `api/question_parser.py`            | Turning intents and entities into parameterized Cypher templates.                                                 |
| `api/answer_searcher.py`            | Running the queries (read routing, timeout) and wording the answers.                                              |
| `api/database.py`                   | `.env` loading, Neo4j connection settings and validation.                                                         |
| `api/build_medicalgraph.py`         | Validating the CSV and replacing the importer-owned graph snapshot; publishing `entities.json`.                   |
| `api/app_logging.py`                | One rotating log file per module.                                                                                 |
| `scripts/evaluate_kg.py`, `eval/`   | The MLOps gate: graph integrity and behavioural evaluation.                                                       |
| `docker/`, `compose.yaml`           | Images and the local stack (nginx web, gunicorn API, Neo4j).                                                      |
| `.github/workflows/`                | Path-filtered CI, MLOps, Docker checks, automatic merging, tag-gated release.                                     |

## Data flow and trust boundaries

```
Browser ──(1)──> nginx web :8080 ──/api/──> gunicorn + Flask API ──(2)──> Neo4j
                                               │
                                               └── entities.json (loaded at start)
medical.csv ──(3)──> importer ──> Neo4j (owned snapshot) + entities.json
```

- (1) Untrusted input enters here: the question. Checked in `api/main.py`; in Docker, nginx rate-limits it first.
- (2) Only parameterized, read-only queries with a timeout.
- (3) The CSV is unverified third-party data; the importer validates and quarantines it.

Threats are in [THREAT.md](THREAT.md), failure modes in [FAILURE.md](FAILURE.md).
