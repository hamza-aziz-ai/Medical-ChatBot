# FEATURE-007: Automatic updates of the local stack

**Goal.** Update and restart the owner's running stack when a release is published, and undo any update that fails (D-021).

**Scope.** `scripts/update_stack.py`, `api/app_logging.py` (its log file), `.gitignore` (`deploy/`), `backend.yml` (tests run when it changes), tests and docs.

**Design.** A Windows scheduled task runs the script every 15 minutes while the owner is signed in. Read-only enrolment records a running published release. Each update checks the release's assets and pulls first, then stops the stack, backs up and checks the graph volume, re-imports, starts the new release and checks that it answers; a phased journal lets a failure or a crash restore the previous release, with the backup only once it was verified. Releases that change `compose.yaml`, downgrades, images changed by hand and failed evaluations are refused before anything changes.

**Status.** Built on branch `feat/update-stack`. The owner enrols and registers the task.

**Open questions.** The full update time on the real graph is not measured yet.

## Log

- 2026-10-25: Design agreed with Codex in council. Offline 231 passed, 9 skipped; live 240 passed. Backup (5.4 s) and restore (2.8 s) tested for real on a disposable Neo4j volume: ownership kept, Neo4j started, data restored. The Windows task and a full update are not run yet.
