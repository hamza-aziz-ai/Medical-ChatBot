# FEATURE-001: Automatic merging when all checks pass

**Goal.** A pull request merges into `main` by itself as soon as every check on its latest commit has passed, with no human review (owner's instruction, D-010).

**Scope.** Branches of this repository only; never forks or drafts. Pull requests whose changes start no CI also merge.

**Design.** `.github/workflows/automerge.yml` runs when `backend`, `frontend`, `mlops` or `docker` finishes, and when a pull request is opened or updated (after a 60 s wait so CI checks can appear). It lists every check run on the head commit except its own, exits if any is still running or did not pass, and otherwise runs `gh pr merge --merge --delete-branch --match-head-commit <sha>`.

**Status.** Shipped in PR #15 (`b59b8ff`).

**Open questions.** The CI-triggered path has not run on a real pull request yet (ASSUMPTIONS.md A-07). Merges made with the workflow token do not re-run the `main` push workflows.

## Log

- 2026-10-25: Built and merged; PR #15 merged itself through the no-CI path about a minute after opening.
