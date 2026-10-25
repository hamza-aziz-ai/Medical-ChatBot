# FEATURE-007: Automatic updates of the local stack

**Goal.** Update and restart the owner's running stack when a release is published, and undo any update that fails (D-021).

**Scope.** `scripts/update_stack.py`, `api/app_logging.py` (its log file), `.gitignore` (`deploy/`), `backend.yml` (tests run when it changes), tests and docs.

**Design.** A Windows scheduled task runs the script every 15 minutes while the owner is signed in. Read-only enrolment records a running published release. Each update checks the release's assets and pulls first, then stops the stack, backs up and checks the graph volume, re-imports, starts the new release and checks that it answers; a phased journal lets a failure or a crash restore the previous release, with the backup only once it was verified. Releases that change `compose.yaml`, downgrades, images changed by hand and failed evaluations are refused before anything changes.

**Status.** Built on branch `feat/update-stack`. The owner enrols and registers the task.

**Open questions.** None; pull and health-check failures are covered by the unit tests only.

## Log

- 2026-10-25: Design agreed with Codex in council. Offline 231 passed, 9 skipped; live 240 passed. Backup (5.4 s) and restore (2.8 s) tested for real on a disposable Neo4j volume: ownership kept, Neo4j started, data restored. The Windows task and a full update are not run yet.
- 2026-10-26: Rollback drill (`scripts/rollback_drill.py`, agreed with Codex in council) on a throwaway Compose project from the real v1.1.4 and v1.1.5 releases, Windows, Docker Desktop. Only release discovery was substituted. Scenario 1: the importer step failed after a committed graph change; the same run restored the backup and v1.1.4 (60 s). Scenario 2: the updater process exited abruptly after the change; a fresh process took the lock and recovered from the journal (57 s). Both times the change was undone, graph counts matched, the old images ran, `/api/health` was ok, a question was answered, and a later run skipped the failed release. Teardown removed the drill project and its volumes.
- 2026-10-26: Drill repeated on the pair v1.1.5 → v1.1.6 (the first release with the plan fingerprint): both scenarios passed (57 s and 56 s); the restored older release answered with its older readiness rule. The owner's stack migrated to v1.1.6 at 2:42 AM and was ready.
