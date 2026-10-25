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
