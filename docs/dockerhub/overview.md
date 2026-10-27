# Mr. Healthcare

A rule-based medical question-answering chatbot (a B.Tech project). It answers basic questions about 658 diseases and their symptoms, causes, prevention, treatments, complications and descriptions from a Neo4j knowledge graph, and says plainly when it cannot answer. Every answer is a fact from the graph; nothing is generated.

**This is a student prototype for local use. It is not medical advice and is not built for public deployment.**

Source, documentation and releases: [github.com/hamza-aziz-ai/Medical-ChatBot](https://github.com/hamza-aziz-ai/Medical-ChatBot)

## Images

| Image | What it runs |
|-------|--------------|
| [`hamzaazizai/medical-chatbot-api`](https://hub.docker.com/r/hamzaazizai/medical-chatbot-api) | The Flask API (gunicorn, one worker) and the graph importer |
| [`hamzaazizai/medical-chatbot-web`](https://hub.docker.com/r/hamzaazizai/medical-chatbot-web) | The Vue 3 page on unprivileged nginx, which forwards `/api/` to the API |

Both images are needed, together with Neo4j 5.26, which the release's `compose.yaml` starts for you.

## Tags

- One version tag per release, for example `1.1.13`; see the Tags tab. There is no `latest`: pull an explicit version.
- Version tags are immutable and never move.
- Each tag is copied byte for byte from `ghcr.io/hamza-aziz-ai/medical-chatbot-api` and `-web` after the release passed its tests, evaluation and an end-to-end smoke test, so the digests are identical on both registries.
- `linux/amd64`. Each image carries an SBOM and SLSA provenance: `docker buildx imagetools inspect hamzaazizai/medical-chatbot-api:<version> --format '{{ json .Provenance }}'`.

## Run it

You need Docker with Compose.

1. From the [GitHub release](https://github.com/hamza-aziz-ai/Medical-ChatBot/releases) of the version you want, download `compose.yaml` and `env.example`. Save `env.example` as `.env` next to `compose.yaml` and set `NEO4J_PASSWORD`.
2. Point Compose at the Docker Hub images (PowerShell: `$env:API_IMAGE = "..."`):

   ```
   export API_IMAGE=hamzaazizai/medical-chatbot-api:<version>
   export WEB_IMAGE=hamzaazizai/medical-chatbot-web:<version>
   export LLM_UNDERSTANDING=off
   ```

3. Start the database, import the graph once, then start everything:

   ```
   docker compose up -d --wait neo4j
   docker compose --profile init run --rm importer
   docker compose up -d
   ```

4. Open http://127.0.0.1:8080 and ask, for example, "what are the symptoms of asthma".

Only the web port is published, on `127.0.0.1` (`WEB_PORT` changes it). `LLM_UNDERSTANDING=off` keeps every question on your machine and uses the rules alone; with it on, the API asks a local Ollama at `host.docker.internal:11434` to help read questions and falls back to the rules whenever that is unavailable.

## Privacy and limits

- Questions travel in the URL, so the API marks every response `Cache-Control: no-store`, and nginx keeps no access or error log. The API logs never contain questions.
- The API is rate-limited in nginx and accepts only short GET questions. It has no user accounts: do not expose it beyond your own machine without adding authentication and HTTPS.
- The bundled dataset's redistribution rights are unverified.
