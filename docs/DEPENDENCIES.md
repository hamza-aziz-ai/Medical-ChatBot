# DEPENDENCIES & SECRETS

Every dependency, why it is here and who maintains it, plus every secret and where it lives. Add an entry before adding a dependency. All versions are pinned exactly.

## Python

| Package             | Version       | Why                                           | Maintainer                        | File                          |
|---------------------|---------------|-----------------------------------------------|-----------------------------------|-------------------------------|
| Flask               | 3.1.3         | HTTP API                                      | Pallets                           | requirements.txt              |
| Flask-Cors          | 6.0.5         | Exact-origin CORS                             | corydolphin / community           | requirements.txt              |
| neo4j               | 6.4.1         | Official Neo4j driver (replaced py2neo)       | Neo4j, Inc.                       | requirements.txt              |
| pyahocorasick       | 2.3.1         | Linear-time multi-name entity matching        | WojciechMula / community          | requirements.txt              |
| gunicorn            | 26.2.0        | Production WSGI server in the API image       | Benoit Chesneau / community       | requirements-deploy.txt       |
| pytest              | 9.0.3         | Tests                                         | pytest-dev                        | requirements-dev.txt          |

## Frontend (npm, Yarn 1.22.22 lockfile)

| Package                                                                 | Version                                         | Why                        | Maintainer                                |
|-------------------------------------------------------------------------|-------------------------------------------------|----------------------------|-------------------------------------------|
| vue                                                                     | 3.5.44                                          | UI framework               | Vue core team                             |
| vite, @vitejs/plugin-vue                                                | 8.3.5, 6.0.10                                   | Build and dev server       | Vite team                                 |
| vitest, @vue/test-utils, happy-dom                                      | 5.0.5, 2.5.1, 21.0.4                            | Component tests            | Vitest team, Vue team, capricorn86        |
| eslint, @eslint/js, eslint-plugin-vue, vue-eslint-parser, globals       | 10.13.0, 10.0.1, 10.11.1, 10.4.1, 17.13.0       | Linting                    | ESLint team, Vue team, sindresorhus       |

## Images and actions

| Item                                                                                        | Pin                                             | Why                                           |
|---------------------------------------------------------------------------------------------|-------------------------------------------------|-----------------------------------------------|
| python:3.14-slim, node:24-alpine, nginxinc/nginx-unprivileged:1.29-alpine, neo4j:5.26       | By digest in `docker/` and `compose.yaml`       | API, build, web and graph containers          |
| actions/checkout, setup-python, setup-node, upload-artifact, download-artifact              | Full commit SHAs                                | CI                                            |
| docker/setup-buildx-action, login-action, build-push-action                                 | Full commit SHAs                                | Release images with SBOM and provenance       |
| rhysd/actionlint:1.7.12                                                                     | Digest in `workflows.yml`; tag locally          | Workflow linting in CI and locally            |

Dependabot watches all of these; open alerts were 0 after the Vue 3 migration.

## Secrets

| Secret                                     | Where it lives                                            | Notes                                                             |
|--------------------------------------------|-----------------------------------------------------------|-------------------------------------------------------------------|
| `NEO4J_PASSWORD`                           | Git-ignored `.env`                                        | Old password rotated and not reused (D11)                         |
| CI Neo4j password `ci-test-password`       | Workflow files                                            | Throwaway, for ephemeral CI containers only                       |
| `GITHUB_TOKEN`                             | Provided by GitHub Actions                                | Write scopes only in the release publish and automerge jobs       |

## External hosts (offline tools only)

| Host and path                                                                                                                         | Used by                                  | Why                                              | Notes                                                                                                                                                                        |
|---------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------|--------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `https://medlineplus.gov/xml.html` and `/xml/mplus_topics_YYYY-MM-DD.xml`                                                             | `scripts/dataset_pilot.py`               | Dataset pilot (D-011): MedlinePlus health topics | Run by hand; never at runtime or in CI. Reuse invited with attribution; health-topic summaries stated as public domain                                                       |
| `https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/releases/doid.obo`                          | `scripts/dataset_pilot.py`               | Dataset pilot (D-011): Disease Ontology          | Run by hand; never at runtime or in CI. CC0 1.0                                                                                                                              |
| `http://localhost:11434/api/chat` (Ollama 0.40.11, owner's install and sign-in) relaying to Ollama's cloud model `gpt-oss:120b-cloud` | `scripts/llm_understanding.py` (planned) | Step-3 experiment (D-026)                        | Run by hand; never at runtime or in CI. Sends only the synthetic questions of `eval/understanding.jsonl`. No API key in the repository; the owner's Ollama holds the sign-in |
