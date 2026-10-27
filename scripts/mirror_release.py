"""Mirror a published release's images from GHCR to Docker Hub, byte for byte (D-030).

    python scripts/mirror_release.py vX.Y.Z      # run by .github/workflows/mirror.yml after each release

GHCR stays the source of truth: release.env, manifest.json, compose and the stack updater never read Docker Hub. This
copies the exact digests the release's manifest.json names, with Skopeo pinned by digest (`copy --all
--preserve-digests` keeps the index, every image and its SBOM and provenance attestations). Version tags only, never
`latest`; a version tag is never overwritten. Every check fails closed: only a confirmed "not found" counts as absent.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKOPEO_IMAGE = "quay.io/skopeo/stable:v1.20@sha256:47853bb9fb24202af9110531ebd6e43c5f97701254ca290596640290d17942f4"
STABLE_TAG = re.compile(r"v\d+\.\d+\.\d+")
DIGEST = r"sha256:[0-9a-f]{64}"
NOT_FOUND = ("manifest unknown", "not found", "name unknown")


class MirrorError(Exception):
    """The mirror cannot proceed safely; the message says why (never a credential)."""


def validate(tag, owner, release, manifest):
    """{image: GHCR digest reference} after checking the release really is this published, passing version."""
    if not STABLE_TAG.fullmatch(tag or ""):
        raise MirrorError(f"{tag!r} is not a stable vX.Y.Z tag")
    if release.get("tagName") != tag or release.get("isDraft") or release.get("isPrerelease"):
        raise MirrorError(f"{tag} is not a published, final release")
    if manifest.get("tag") != tag or manifest.get("evaluation_passed") is not True:
        raise MirrorError(f"{tag}'s manifest does not match the tag or did not pass evaluation")
    images = manifest.get("images")
    if not isinstance(images, dict) or set(images) != {"api", "web"}:
        raise MirrorError("the manifest must name exactly the api and web images")
    sources = {}
    for image, ref in images.items():
        # Each image must come from its own GHCR repository, by digest: never a tag, never the other image.
        if not isinstance(ref, str) or not re.fullmatch(rf"ghcr\.io/{re.escape(owner.lower())}/medical-chatbot-{image}@{DIGEST}", ref):
            raise MirrorError(f"the manifest's {image} image is not ghcr.io/{owner}/medical-chatbot-{image}@sha256:...")
        sources[image] = ref
    return sources


class Skopeo:
    """Registry access through the pinned Skopeo image, with Docker's credentials mounted read-only."""

    def __init__(self, authfile, docker_args=()):
        # docker_args lets the live test reach a throwaway local registry (network, registries.conf); empty in CI.
        self.authfile, self.docker_args = authfile, tuple(docker_args)

    def run(self, *args):
        command = ["docker", "run", "--rm", "-v", f"{self.authfile}:/auth.json:ro", *self.docker_args, SKOPEO_IMAGE, *args]
        return subprocess.run(command, capture_output=True, timeout=600)

    def digest(self, ref):
        """The digest of ref's manifest, or None only when the registry confirms it does not exist."""
        result = self.run("inspect", "--raw", "--authfile", "/auth.json", f"docker://{ref}")
        if result.returncode == 0:
            return "sha256:" + hashlib.sha256(result.stdout).hexdigest()
        error = result.stderr.decode("utf-8", "replace").lower()
        if any(marker in error for marker in NOT_FOUND):
            return None
        raise MirrorError(f"could not look up {ref} (exit {result.returncode}); treated as a failure, not as absent")

    def copy(self, source, destination):
        result = self.run("copy", "--all", "--preserve-digests", "--authfile", "/auth.json",
                          f"docker://{source}", f"docker://{destination}")
        if result.returncode != 0:
            raise MirrorError(f"copying to {destination} failed (exit {result.returncode})")


def mirror(sources, namespace, version, registry, log=print):
    """Per image: same digest skips, a different digest fails (never overwrite), a confirmed absence copies and is
    then verified. Each image is decided on its own, so a retry completes a partial mirror."""
    for image, source in sorted(sources.items()):
        want = source.split("@", 1)[1]
        destination = f"docker.io/{namespace}/medical-chatbot-{image}:{version}"
        have = registry.digest(destination)
        if have == want:
            log(f"{destination} already holds {want}; skipped")
            continue
        if have is not None:
            raise MirrorError(f"{destination} already holds {have}, not {want}; version tags are never overwritten")
        registry.copy(source, destination)
        copied = registry.digest(destination)
        if copied != want:
            raise MirrorError(f"{destination} holds {copied} after copying, not {want}")
        log(f"{destination} now holds {want}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: mirror_release.py vX.Y.Z", file=sys.stderr)
        return 2
    tag = argv[0]
    namespace, owner = os.environ.get("DOCKERHUB_USERNAME", ""), os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    if not namespace:
        print("Docker Hub mirroring is not configured: set the DOCKERHUB_USERNAME repository variable", file=sys.stderr)
        return 1
    try:
        release = json.loads(Path(os.environ["RELEASE_JSON"]).read_text(encoding="utf-8"))
        manifest = json.loads(Path(os.environ["MANIFEST_JSON"]).read_text(encoding="utf-8"))
        sources = validate(tag, owner, release, manifest)
        mirror(sources, namespace, tag[1:], Skopeo(os.environ["DOCKER_AUTHFILE"]))
    except (OSError, ValueError, KeyError, MirrorError) as error:
        print(f"Mirror failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
