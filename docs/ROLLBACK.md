# ROLLBACK

How to undo a change that breaks something.

## Last known good

- Release: `v1.0.0` (commit `6300fca`), images `ghcr.io/hamza-aziz-ai/medical-chatbot-api@sha256:8cfb7291…` and `ghcr.io/hamza-aziz-ai/medical-chatbot-web@sha256:414092e2…` (full digests in the release's `release.env`).
- Current `main`: `b59b8ff` (integrity fixes and automerge). Update this line after each risky change.

## Code

1. Find the merge commit of the bad pull request: `git log --merges --oneline`.
2. Revert it on a branch: `git revert -m 1 <merge-commit>`, push, and open a PR. CI runs, and `automerge` merges the revert when it passes.
3. Never force-push `main` or delete a tag.

## Running stack (Docker)

1. Point the stack at the last good images: copy `API_IMAGE` and `WEB_IMAGE` from that release's `release.env` into `.env`, then `docker compose up -d`.
2. Check the page and one question (see TESTING.md, manual path).

## Graph data

The importer replaces its snapshot, so a bad import is undone by importing again from a good version.

1. Before any import: stop the stack and back up the `neo4j-data` volume (for example `docker run --rm -v medical-chatbot_neo4j-data:/data -v "$PWD":/backup alpine tar czf /backup/neo4j-data.tgz -C /data .`).
2. To undo: restore that archive into the volume, or run the importer from the last good image: `API_IMAGE=<good digest> docker compose --profile init run --rm importer`.
3. Restart `api` so it loads the matching `entities.json`.

## Re-check afterwards

Run the commands in TESTING.md that cover the area you rolled back, and the manual customer path.
