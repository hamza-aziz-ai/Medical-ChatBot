# FEATURE-006: Automatic releases

**Goal.** Release without pushing tags by hand, once every gate passes (D-019).

**Scope.** `scripts/next_release.py`, `.github/workflows/autorelease.yml` (new), `release.yml` (new-version path, attempt-specific image tags, tag created in publish), `workflows.yml` (actionlint in CI), `backend.yml` and `automerge.yml` (paths and the new check), tests and docs.

**Design.** The planner compares `main` with the last published release and releases only when shipped files changed. It picks patch, or the highest `release:minor` / `release:major` label on the merged pull requests, or the manual `bump` input, and never reuses a version. It stops on an incomplete publication or a failed lookup. `release.yml` runs every gate at the chosen commit and creates the tag only in publish.

**Status.** Built on branch `feat/autorelease`, started by hand only. Next: cut v1.1.0 through it, then enable the trigger after `automerge` once the owner accepts batching.

**Open questions.** Whether the owner accepts batching (several merges in one release) or wants one release per merge.

## Log

- 2026-10-25: Design agreed with Codex in council. Offline 198 passed, 9 skipped; actionlint clean. Hosted behaviour not yet run.
