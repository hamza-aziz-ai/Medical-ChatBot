# ROLLBACK

How to undo a change that breaks something.

## Last known good

- Release: `v1.0.0` (commit `6300fca`), images `ghcr.io/hamza-aziz-ai/medical-chatbot-api@sha256:8cfb7291…` and `ghcr.io/hamza-aziz-ai/medical-chatbot-web@sha256:414092e2…` (full digests in the release's `release.env`).
- Current `main`: `b59b8ff` (integrity fixes and automerge). Update this line after each risky change.

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
