"""Static checks on the release workflow (D-019)."""
import re
from pathlib import Path

RELEASE = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_release_images_are_pushed_under_tags_unique_to_the_attempt():
    # CONSTRAINTS.md: never overwrite a published image tag. A retried release must not reuse a pushed tag.
    pushed = re.findall(r"^\s+tags:\s*(\$\{\{ env\.IMAGE_PREFIX \}\}.+?)\s*$", RELEASE, flags=re.MULTILINE)
    assert len(pushed) == 2
    for tag in pushed:
        assert tag.endswith(":sha-${{ needs.resolve.outputs.sha }}-${{ github.run_id }}-${{ github.run_attempt }}"), tag


def test_a_new_version_tag_is_created_only_in_publish_after_the_smoke_test():
    publish = RELEASE[RELEASE.index("\n  publish:"):]
    assert "needs: [resolve, images, smoke]" in publish
    assert "git/refs" in publish and "git/refs" not in RELEASE[:RELEASE.index("\n  publish:")]


AUTORELEASE = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "autorelease.yml").read_text(encoding="utf-8")


def test_the_release_chain_continues_only_after_a_successful_release():
    continue_job = AUTORELEASE[AUTORELEASE.index("\n  continue:"):]
    assert "needs: release" in continue_job
    assert "if: needs.release.result == 'success'" in continue_job
    assert "gh workflow run autorelease.yml --ref main -f bump=auto" in continue_job
    # Only the continue job, and the release call's ceiling for starting the Docker Hub mirror (D-030), may start workflows.
    release_job = AUTORELEASE[AUTORELEASE.index("\n  release:"):AUTORELEASE.index("\n  continue:")]
    assert AUTORELEASE.count("actions: write") == 2 and "actions: write" in continue_job and "actions: write" in release_job


def test_automatic_runs_never_drain_the_backlog_before_the_bootstrap_release():
    assert "--require-baseline v1.1.0" in AUTORELEASE
