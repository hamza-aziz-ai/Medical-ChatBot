# FEATURE-019: The updater removes old release images

**Goal.** Old release images do not pile up on the VM or the local machine; nobody has to clean them up.

**Scope.** `scripts/update_stack.py` (`prune_images()`, called from `prune()` after every successful update) and the updater tests in `tests/test_update_stack.py`.

**Design.** D-039. The images named in the kept release folders (`deploy/releases/v*/release.env`, the newest `KEEP` plus the recorded release) are kept by image ID; every other image from `ghcr.io/hamza-aziz-ai/medical-chatbot-api` or `-web` is removed with `docker rmi`, without `-f`, so an image a container still uses is refused and stays.

**Status.** Built 2026-10-30; the VM's 22 older images go at the next successful update.

**Open questions.** None.

## Log

- 2026-10-30: Built. 423 Python tests pass, 14 skipped; the fake Docker now tracks pulled images, and the pruning test checks that only the two kept releases' images stay. On the VM, `docker image inspect --format {{.Id}}` of a release's digests matches the IDs `docker images --no-trunc` lists. The rollback drill was not rerun: it exercises only failure paths, which never prune.
