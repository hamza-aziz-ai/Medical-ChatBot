# FEATURE-020: The hosted updater follows the releases it deploys

**Goal.** A change to the updater reaches the VM by itself, with the next release.

**Scope.** `scripts/update_stack.py` (`follow_release()`, called from `deploy()` after a committed hosted update) and the updater tests in `tests/test_update_stack.py`.

**Design.** D-040. After the update is committed: read the release's `manifest.json` commit, skip if the clone has local changes to tracked files, fetch the release tag, check that it names that commit, check it out detached, and check that the new `update_stack.py` and `app_logging.py` compile; otherwise go back. Failures only log a warning.

**Status.** Live since v1.1.26 (2026-10-30). The VM's clone was moved to `main` by hand twice to bring this code there; it has followed the releases by itself since.

**Open questions.** None.

## Log

- 2026-10-30: Built. 427 Python tests pass, 14 skipped; new tests cover the hosted move, no move in local mode, a failed fetch or compile check leaving the clone in place, and a clone with local changes. Removing the call or the local-changes guard fails a test. Against a real clone at PR #68 and the real v1.1.25 manifest, the clone moved to e7472d4, the release's commit. On the VM the timer runs as `ubuntu`, who owns the clone (git 2.43).
- 2026-10-30: Verified on the VM: the v1.1.26 update moved the clone to a564991, and the 22:10 IST timer run finished cleanly from that code (A-28).
