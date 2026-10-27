# ROLLBACK

How to undo a change that breaks something.

## Last known good

- Release: `v1.1.7` (commit `dc13ebe`), images `ghcr.io/hamza-aziz-ai/medical-chatbot-api@sha256:c286127b…` and `ghcr.io/hamza-aziz-ai/medical-chatbot-web@sha256:8666a1e6…` (full digests in the release's `release.env`). Running on the owner's stack since 2026-10-26 with `/api/health` ok. Its graph needs a re-import from the same release (plan fingerprint, D-023); `scripts/update_stack.py` does that, and restores a release's own graph backup on rollback.
- Current `main`: `b3a8934`. Update this line after each risky change.

## Code

1. Find the merge commit of the bad pull request: `git log --merges --oneline`.
2. Revert it on a branch: `git revert -m 1 <merge-commit>`, push, and open a PR. CI runs, and `automerge` merges the revert when it passes.
3. Never force-push `main` or delete a tag.

## A release that stopped part-way

`autorelease.yml` stops, and changes nothing, when the newest version tag on `main` is not fully published. Each case names its fix in the run log.

1. **A draft release exists.** Check that the draft's `manifest.json` names the tag's commit and the image digests from the run's smoke test. If they match, add any missing version image tag (`docker buildx imagetools create -t ghcr.io/hamza-aziz-ai/medical-chatbot-<api|web>:<version> <image>@<digest>`) and publish the draft (`gh release edit <tag> --draft=false`). If they do not match, delete the draft; the tag stays and its version is never reused.
2. **Version images but no release.** Leave the tag and the images untouched. Publish the next unused version by hand: run `release.yml` from the Actions tab with `tag` set to that version and `sha` set to a commit on `main`. Every gate runs, and automation resumes once it is published.
3. **A tag with no release and no version images** (a run died between creating the tag and drafting) needs nothing: the next run skips that version.

Staging images named `sha-<commit>-<run>-<attempt>` from failed attempts are never published and may be deleted from the package settings.

## A merge whose release keeps failing

Releases go in merge order, so a merge whose release fails blocks the merges after it. A failure before publish creates no tag: start `autorelease.yml` again from the Actions tab once the cause is fixed (for example a flaky test or an outage). If the merge itself cannot pass, fixing forward does not help, because the old commit never changes. Publish a later commit by hand instead: run `release.yml` with `tag` set to the next unused version and `sha` set to a later commit on `main`. That deliberately skips separate releases for the merges in between, and automation continues after it.

## Docker Hub mirror (D-030)

Docker Hub is never read by compose or the updater, so it never needs a rollback for the owner's stack. Version tags are never overwritten: to withdraw a bad version from Docker Hub, the owner deletes its tags on Docker Hub (the token has no Delete scope) and a fixed version is released. To stop mirroring, delete the `DOCKERHUB_USERNAME` variable (each run then fails as not configured) or disable `mirror.yml` in the Actions tab; to undo the code, revert its pull request.

To undo a wrong Docker Hub description, revert the change to `docs/dockerhub/`; the next `dockerhub-metadata` run restores the text. To stop the sync, disable `dockerhub-metadata.yml` in the Actions tab.

## The hosted stack (D-032)

On the VM, `hosted` is the Compose command from step 3 of [hosting/oracle/README.md](../hosting/oracle/README.md). `hosted stop cloudflared` closes public access at once. If a recovery failed, the updater kept public access closed and left `deploy/journal.json` with `recovery_failed`. Choose the release to run, then follow step 3 with that tag: download its hosted assets, run its importer, start `api web`, and check `/api/health` and a question on 127.0.0.1. Then run `hosted up -d cloudflared`, delete `deploy/journal.json` and enrol again with `python3 scripts/update_stack.py --enroll <tag> --hosted`. A wrong graph is fixed the same way: stop `cloudflared`, `web` and `api`, and run the importer of the release you trust.

## Running stack (Docker)

1. Point the stack at the last good images: copy `API_IMAGE` and `WEB_IMAGE` from that release's `release.env` into `.env`, then `docker compose up -d`.
2. Check the page and one question (see TESTING.md, manual path).

## The language model (D-027)

1. Set `LLM_UNDERSTANDING=off` in `.env` (or `OLLAMA_URL`/`LLM_MODEL` to change where it goes), then recreate the API: `docker compose up -d api`. Questions are then answered by the rules alone; nothing else changes.
2. Check one paraphrase: "Why this answer?" no longer says a language model read it.

## The stack updater

Verified by a drill on 2026-10-26 (`python scripts/rollback_drill.py`, a throwaway stack): a failure after the graph changed, and the updater process dying mid-update, both ended with the backup and the previous release restored. Run the drill again after changing `update_stack.py`.

`scripts/update_stack.py` restores the previous release by itself when an update fails, and does not retry that release (`deploy/failed.json`; delete it to allow a retry). If it cannot restore, it leaves the app stopped and marks `deploy/journal.json` with `recovery_failed`, and every later run stops until you act:

1. Disable the scheduled task.
2. The journal names the previous release, its `compose.yaml` folder under `deploy/releases/`, and the graph backup under `deploy/backups/`.
3. Restore the backup into the `medical-chatbot_neo4j-data` volume with the stack stopped (`docker run --rm -v medical-chatbot_neo4j-data:/data -v <backups folder>:/backup --entrypoint sh <neo4j image from compose.yaml> -c "find /data -mindepth 1 -delete && tar xzpf /backup/<archive> -C /data"`).
4. Start the previous release: set `API_IMAGE` and `WEB_IMAGE` from its `release.env` and run `docker compose -f deploy/releases/<tag>/compose.yaml --project-directory . up -d`.
5. Check the page and one question, delete `deploy/journal.json`, and enable the task again.

Backups and release folders still referenced by the recorded release or a journal are never pruned.

## Graph data

If an import stopped part-way ("Graph committed, but dictionary publication failed" or "commit outcome is unknown"): stop serving, fix the error, rerun the same import, restart the API, and check that `GET /health` returns ok (D-023). Run one import at a time.

The importer replaces its snapshot, so a bad import is undone by importing again from a good version.

1. Before any import: stop the stack and back up the `neo4j-data` volume (for example `docker run --rm -v medical-chatbot_neo4j-data:/data -v "$PWD":/backup alpine tar czf /backup/neo4j-data.tgz -C /data .`).
2. To undo: restore that archive into the volume, or run the importer from the last good image: `API_IMAGE=<good digest> docker compose --profile init run --rm importer`.
3. Restart `api` so it loads the matching `entities.json`.

## Re-check afterwards

Run the commands in TESTING.md that cover the area you rolled back, and the manual customer path.
