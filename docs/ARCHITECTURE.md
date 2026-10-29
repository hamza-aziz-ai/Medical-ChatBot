# ARCHITECTURE

One-page map. Deeper detail: the README and its diagrams, the guides in [guides/](guides/), [FLOW.md](FLOW.md), [DATA.md](DATA.md) and the two architecture pages (Solution Architecture and Software & System Design).

## What it is

A rule-based medical question-answering chatbot. It finds disease and symptom names in a question, works out what is being asked from keywords, and answers from a Neo4j knowledge graph built from `api/data/medical.csv`. If it cannot answer from the graph, it says so instead of guessing. There is no machine-learning model at runtime.

## Solution architecture

The whole solution: how a change is checked and released, where the released images and files live, and how they run on the public site and, optionally, on one machine. The README has a simpler version.

```mermaid
flowchart LR
  classDef actor fill:#e3f2f1,stroke:#0b6e6e,stroke-width:2px,color:#0f1b2d
  classDef pipe fill:#eef2ff,stroke:#4f46e5,color:#1e1b4b
  classDef ctr fill:#ffffff,stroke:#0b6e6e,color:#0f1b2d
  classDef store fill:#f4f6f9,stroke:#536175,color:#0f1b2d
  classDef ext fill:#fff4e5,stroke:#c77700,color:#4a2a00

  subgraph LOCAL["`**Local machine** (optional)`"]
    direction LR
    LUPD["`**Windows scheduled task**: update_stack.py, backs up neo4j-data first (D-021)`"]:::ctr
    LWEB["`**web**: nginx on 127.0.0.1:8080`"]:::ctr
    LAPI["`**api**: gunicorn + Flask`"]:::ctr
    LN4[("`**neo4j 5.26** container, neo4j-data volume, rebuilt by the importer`")]:::store
    HOLL["`**Ollama** on the host`"]:::ext
    LWEB --> LAPI --> LN4
    LAPI --> HOLL
  end

  DEV(["`**Owner or coding agent**`"]):::actor

  subgraph GH["`**GitHub CI/CD**`"]
    direction TB
    PR["`**Pull request** from a branch`"]:::pipe
    CHK["`**Path-filtered checks**: backend.yml pytest, frontend.yml lint + tests + build, mlops.yml data gates + live Neo4j 5 and 4.4 + import and evaluation, docker.yml images + Compose smoke, workflows.yml actionlint`"]:::pipe
    AM["`**automerge.yml**: merges into main when every check on the latest commit passed`"]:::pipe
    AR["`**autorelease.yml**: oldest unreleased merge that ships files, next SemVer (D-019, D-034)`"]:::pipe
    RL["`**release.yml**: re-runs the gates on that commit, builds and pushes images with SBOM and provenance, smoke-tests the digests, then tags and publishes`"]:::pipe
    MR["`**mirror.yml**: copies by digest, never rebuilds (D-030)`"]:::pipe
    PR --> CHK --> AM --> AR --> RL --> MR
  end

  subgraph REG["`**Artifacts**`"]
    direction TB
    GREL[("`**GitHub Release**: compose files, release.env digests, frontend build, entities.json, evaluation report`")]:::store
    GHCR[("`**GHCR**: api and web images, version tags never overwritten`")]:::store
    HUB[("`**Docker Hub**: byte-for-byte copy`")]:::store
  end

  V(["`**Visitor's browser**`"]):::actor

  subgraph CF["`**Cloudflare**`"]
    direction TB
    EDGE["`**Edge**: TLS ends, HSTS, sets CF-Connecting-IP, /api/* never cached`"]:::ext
    WK["`**Maintenance Worker** on page routes: the site's own 503 page while the origin is unreachable; /api/* routed past it; logs off (D-035)`"]:::ext
    EDGE -.->|"`origin unreachable`"| WK
  end

  subgraph VM["`**Oracle Cloud VM**`"]
    direction LR
    CFD["`**cloudflared** 10.213.0.2: dials out, keeps no logs`"]:::ctr
    WEB["`**web** 10.213.0.3: nginx serves the page and 404.html; trusts CF-Connecting-IP only from 10.213.0.2; 10 r/s per visitor, 16 API requests in flight; no logs`"]:::ctr
    API["`**api**: gunicorn, 1 worker, Flask; 300 MB; logs to the api-logs volume`"]:::ctr
    OLL["`**ollama**: signed in (ollama-identity volume), no published port, 6 calls a minute in total (D-033)`"]:::ctr
    CFD --> WEB -->|"`/api/`"| API -->|"`question + candidate names, 2 s`"| OLL
    subgraph UPDS["`**Updates**`"]
      direction LR
      UPD["`**Updater**: systemd timer every 15 min, update_stack.py hosted mode; closes the tunnel, rebuilds the graph, checks, reopens; rolls back on failure`"]:::ctr
      IMP["`**importer** (profile init): validates the CSV, replaces the graph`"]:::ctr
      UPD -.->|"`runs`"| IMP
    end
  end

  subgraph SVC["`**Managed services**`"]
    direction TB
    AURA[("`**Neo4j AuraDB Free**: the knowledge graph`")]:::ext
    OCL["`**Ollama cloud**: gpt-oss:120b`"]:::ext
  end

  DEV --> PR
  RL --> GREL
  RL --> GHCR
  MR --> HUB
  GHCR -.->|"`pull by digest`"| UPD
  GREL -.->|"`newer release`"| UPD
  GHCR -.->|"`pull release`"| LUPD
  V -->|"`HTTPS`"| EDGE
  EDGE ==>|"`outbound tunnel`"| CFD
  API -->|"`neo4j+s, read-only Cypher, 5 s`"| AURA
  IMP -->|"`one write transaction`"| AURA
  OLL -->|"`HTTPS`"| OCL
```

- **Colours:** pale teal for actors, blue for CI/CD workflows, white for containers and processes, grey for stored artifacts and volumes, orange for services run by others (Cloudflare, Neo4j AuraDB, Ollama's cloud).
- **Lines:** solid lines carry requests and data, the thick line is the Cloudflare tunnel, dotted lines are the update and fallback paths.
- **Reading order:** left to right, a change goes from the owner through GitHub's checks and release to the artifacts; the updaters on the VM and on a local machine pull those artifacts. A visitor enters through Cloudflare; the VM reaches out only to the managed services.
- **Trust boundaries:** the internet ends at Cloudflare; the VM accepts only the tunnel that cloudflared opens outward; nginx believes `CF-Connecting-IP` only from cloudflared's fixed address; questions leave the VM only to the model, and only the graph's facts reach a visitor. Details in [THREAT.md](THREAT.md).
- **Decisions:** delivery D-019, D-030, D-034; hosting D-032, D-033; the maintenance page D-035; an open page during updates D-037; the local updater D-021 ([DECISIONS.md](DECISIONS.md)).

## Modules and what they own

| Module                                                          | Owns                                                                                                                                                                 |
|-----------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `frontend/` (Vue 3, Vite)                                       | The page: chat panel and About panel. Talks to the API through `src/chatApi.mjs`; follows updates through `src/liveUpdate.mjs` (D-037).                                                                                    |
| `api/main.py`                                                   | The HTTP boundary: CORS, input limits, JSON errors, request logging without questions. No authentication (D-013).                                                    |
| `api/chatbot_graph_logic.py`                                    | One question in, one answer or abstention out.                                                                                                                       |
| `api/question_classifier.py`                                    | Entity matching (Aho-Corasick over `api/dictionary/entities.json`) and keyword intents.                                                                              |
| `api/question_parser.py`                                        | Turning intents and entities into parameterized Cypher templates.                                                                                                    |
| `api/answer_searcher.py`                                        | Running the queries (read routing, timeout) and wording the answers.                                                                                                 |
| `api/text_format.py`                                            | Headings and numbered points found in long text without changing a word (D-028); the prose projection and formatter identity for rewordings (D-029).                 |
| `api/understanding.py`                                          | The language-model contract (D-027): candidates, frozen prompt, validator, bounded transport, attempt budgets, breaker.                                              |
| `api/database.py`                                               | `.env` loading, Neo4j connection settings and validation.                                                                                                            |
| `api/build_medicalgraph.py`                                     | Validating the CSV and replacing the importer-owned graph snapshot; publishing `entities.json`.                                                                      |
| `api/app_logging.py`                                            | One rotating log file per module.                                                                                                                                    |
| `scripts/llm_understanding.py`, `scripts/reword_answers.py`     | Offline only: the language-model evaluation rounds (D-026, D-027) and the reviewed rewording pipeline (D-029).                                                       |
| `scripts/mirror_release.py`, `.github/workflows/mirror.yml`     | Copies each published release's GHCR digests to Docker Hub, never rebuilding or overwriting (D-030).                                                                 |
| `hosting/oracle/`, `scripts/hosted_check.sh`                    | The public hosted stack (D-032): its compose file, released as `compose.hosted.yaml`; the updater's systemd units; the setup guide; the CI check of its proxy trust. |
| `scripts/evaluate_kg.py`, `eval/`                               | The MLOps gate: graph integrity and behavioural evaluation.                                                                                                          |
| `docker/`, `compose.yaml`                                       | Images and the local stack (nginx web, gunicorn API, Neo4j).                                                                                                         |
| `.github/workflows/`                                            | Path-filtered CI, MLOps, Docker checks, automatic merging, tag-gated release.                                                                                        |

## Data flow and trust boundaries

```
Browser ──(1)──> nginx web :8080 ──/api/──> gunicorn + Flask API ──(2)──> Neo4j
                                               │
                                               ├── entities.json (loaded at start)
                                               └──(4)──> Ollama on the host ──> Ollama's cloud model (D-027, when on)
medical.csv ──(3)──> importer ──> Neo4j (owned snapshot) + entities.json
```

- (1) Untrusted input enters here: the question. Checked in `api/main.py`; in Docker, nginx rate-limits it first.
- (2) Only parameterized, read-only queries with a timeout.
- (3) The CSV is unverified third-party data; the importer validates and quarantines it.
- (4) The question and candidate names leave the machine. The reply is untrusted: only candidate ids and allowed intents are accepted, and nothing it writes reaches the user.

Threats are in [THREAT.md](THREAT.md), failure modes in [FAILURE.md](FAILURE.md).
