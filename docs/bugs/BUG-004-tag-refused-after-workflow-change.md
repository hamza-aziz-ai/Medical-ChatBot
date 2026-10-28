# BUG-004: A release tag is refused when workflows changed after the released merge

**Symptom.** The v1.1.14 release (the merge of PR #62) passed every gate, then `publish` failed creating its tag: `gh: Resource not accessible by integration (HTTP 403)`. Releases go in merge order, so every later release would wait behind it.

**Repro.** Merge a shippable pull request, then merge a pull request that changes `.github/workflows/` before the first one's release reaches `publish`. The release run creates the tag for the first merge with the workflow token and gets 403.

**Root cause (likely, not confirmed by GitHub documentation).** GitHub refuses refs created by the workflow token, which has no `workflows` permission, when the target commit's workflow files differ from those on the default branch. PR #63 changed `release.yml` after PR #62's merge. Earlier releases never hit this because no workflow change landed between a merge and its release.

**Workaround used (owner-approved, 2026-10-27).** The owner authorised pushing tag `v1.1.14` at `8a04374` by hand. A tag push runs `release.yml` from the tagged commit, which still had the bug PR #63 fixed, so that run failed too. Then `release.yml` was started by hand from `main` with `tag=v1.1.14` (its documented "existing tag" path); every gate passed and v1.1.14 was published.

**Fix.** The owner chose waiting (D-034). `scripts/next_release.py` now releases the first commit on main, at or after the oldest pending merge, whose workflow files match main's; when a workflow change landed after a merge, that merge ships in the release of the later commit. No workflow file changed, so the fix cannot trigger the bug itself.

## Log

- 2026-10-27: Found during the v1.1.14 release; worked around with the owner's approval.
- 2026-10-28: Fixed (D-034). Tests cover a merge behind a later workflow change (released with it, then later merges alone again) and the unchanged case; replaying the incident picks `7d4737b`, whose workflows match.
