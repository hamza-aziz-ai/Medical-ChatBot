# FEATURE-014: Release images on Docker Hub

**Goal.** Publish every release's images to Docker Hub as well as GHCR, automatically, with no manual build or push (D-030).

**Scope.** `.github/workflows/mirror.yml` (new), `.github/workflows/release.yml` (starts the mirror after publishing), `.github/workflows/autorelease.yml` (permission ceiling), `scripts/mirror_release.py`, `tests/test_mirror_release.py`, `tests/test_workflows.py`.

**Design.** See D-030: a separate run copies the release manifest's GHCR digests to `docker.io/hamzaazizai/medical-chatbot-api` and `-web` with Skopeo pinned by digest, version tags only, failing closed on every uncertain lookup. GHCR stays the source for compose and the updater.

**Status.** Live: v1.1.13 backfilled; every later release is mirrored automatically.

**Open questions.** Whether the owner turns on Docker Hub's immutable tags; whether a `latest` tag is ever wanted.

## Log

- 2026-10-27: Built. Unit tests for validation and the per-image decisions; live copy of v1.1.13's API index from GHCR into a throwaway registry kept the digest, the attestation manifest and every blob.
- 2026-10-27: Merged (PR #58). The v1.1.13 backfill (run 40508274098) copied both images; Docker Hub and GHCR index digests match, and both repositories are public.
