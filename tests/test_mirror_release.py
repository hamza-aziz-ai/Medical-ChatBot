"""The Docker Hub mirror (D-030): release validation, the per-image decision table, and an opt-in live copy."""
import importlib.util
import json
import os
import re
import subprocess
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mirror_release", ROOT / "scripts" / "mirror_release.py")
mr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mr)

API = "sha256:" + "a" * 64
WEB = "sha256:" + "b" * 64
OTHER = "sha256:" + "c" * 64


def release(**changes):
    return {"tagName": "v1.2.3", "isDraft": False, "isPrerelease": False, **changes}


def manifest(**changes):
    return {"tag": "v1.2.3", "evaluation_passed": True,
            "images": {"api": f"ghcr.io/hamza-aziz-ai/medical-chatbot-api@{API}",
                       "web": f"ghcr.io/hamza-aziz-ai/medical-chatbot-web@{WEB}"}, **changes}


def test_a_published_passing_release_yields_its_two_digests():
    assert mr.validate("v1.2.3", "hamza-aziz-ai", release(), manifest()) == manifest()["images"]


@pytest.mark.parametrize("tag, rel, man", [
    ("v1.2.3-rc1", release(tagName="v1.2.3-rc1"), manifest(tag="v1.2.3-rc1")),
    ("v1.2.3", release(isDraft=True), manifest()),
    ("v1.2.3", release(isPrerelease=True), manifest()),
    ("v1.2.3", release(tagName="v1.2.4"), manifest()),
    ("v1.2.3", release(), manifest(tag="v1.2.4")),
    ("v1.2.3", release(), manifest(evaluation_passed=False)),
    ("v1.2.3", release(), manifest(evaluation_passed="true")),
    ("v1.2.3", release(), manifest(images={"api": manifest()["images"]["api"]})),
    # Swapped repositories, a tag instead of a digest, another owner, another registry.
    ("v1.2.3", release(), manifest(images={"api": f"ghcr.io/hamza-aziz-ai/medical-chatbot-web@{WEB}",
                                           "web": f"ghcr.io/hamza-aziz-ai/medical-chatbot-api@{API}"})),
    ("v1.2.3", release(), manifest(images={"api": "ghcr.io/hamza-aziz-ai/medical-chatbot-api:1.2.3",
                                           "web": manifest()["images"]["web"]})),
    ("v1.2.3", release(), manifest(images={"api": f"ghcr.io/someone/medical-chatbot-api@{API}",
                                           "web": manifest()["images"]["web"]})),
    ("v1.2.3", release(), manifest(images={"api": f"docker.io/hamza-aziz-ai/medical-chatbot-api@{API}",
                                           "web": manifest()["images"]["web"]})),
])
def test_anything_but_a_published_passing_release_from_ghcr_is_refused(tag, rel, man):
    with pytest.raises(mr.MirrorError):
        mr.validate(tag, "hamza-aziz-ai", rel, man)


class FakeRegistry:
    """Docker Hub as a dict of tag -> digest; a lookup raises for the refs in `broken`."""

    def __init__(self, tags=None, broken=(), copy_result=None):
        self.tags, self.broken, self.copy_result, self.copies = dict(tags or {}), set(broken), copy_result, []

    def digest(self, ref):
        if ref in self.broken:
            raise mr.MirrorError("lookup failed")
        return self.tags.get(ref)

    def copy(self, source, destination):
        self.copies.append(destination)
        self.tags[destination] = self.copy_result or source.split("@", 1)[1]


SOURCES = manifest()["images"]
API_TAG = "docker.io/hamzaazizai/medical-chatbot-api:1.2.3"
WEB_TAG = "docker.io/hamzaazizai/medical-chatbot-web:1.2.3"


def run(registry):
    mr.mirror(SOURCES, "hamzaazizai", "1.2.3", registry, log=lambda line: None)


def test_missing_tags_are_copied_and_a_rerun_copies_nothing():
    registry = FakeRegistry()
    run(registry)
    assert registry.copies == [API_TAG, WEB_TAG]
    run(registry)
    assert registry.copies == [API_TAG, WEB_TAG]


def test_a_partial_mirror_is_completed_by_a_retry():
    registry = FakeRegistry({API_TAG: API})
    run(registry)
    assert registry.copies == [WEB_TAG]


def test_a_tag_holding_another_digest_is_never_overwritten():
    registry = FakeRegistry({API_TAG: OTHER})
    with pytest.raises(mr.MirrorError, match="never overwritten"):
        run(registry)
    assert registry.copies == []


def test_a_failed_lookup_is_a_failure_not_an_absence():
    registry = FakeRegistry(broken={API_TAG})
    with pytest.raises(mr.MirrorError):
        run(registry)
    assert registry.copies == []


def test_a_copy_that_lands_another_digest_fails():
    with pytest.raises(mr.MirrorError, match="after copying"):
        run(FakeRegistry(copy_result=OTHER))


def test_only_a_confirmed_not_found_counts_as_absent(monkeypatch):
    skopeo = mr.Skopeo("auth.json")
    for stderr, absent in [(b"manifest unknown", True), (b"name unknown: repository name not known", True),
                           (b"unauthorized: authentication required", False), (b"toomanyrequests", False),
                           (b"dial tcp: i/o timeout", False)]:
        monkeypatch.setattr(skopeo, "run", lambda *args, e=stderr: subprocess.CompletedProcess(args, 1, b"", e))
        if absent:
            assert skopeo.digest("docker.io/x/y:1") is None
        else:
            with pytest.raises(mr.MirrorError):
                skopeo.digest("docker.io/x/y:1")


def test_main_fails_visibly_when_not_configured(monkeypatch, capsys):
    monkeypatch.delenv("DOCKERHUB_USERNAME", raising=False)
    assert mr.main(["v1.2.3"]) == 1
    assert "not configured" in capsys.readouterr().err


WORKFLOW = (ROOT / ".github" / "workflows" / "mirror.yml").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_the_mirror_copies_and_never_builds():
    assert "build-push-action" not in WORKFLOW and "docker build" not in WORKFLOW and "docker push" not in WORKFLOW
    assert "imagetools create" not in WORKFLOW
    # Only the mirror workflow reads the Docker Hub token; the release chain forwards no secrets.
    assert "secrets.DOCKERHUB_TOKEN" in WORKFLOW and "DOCKERHUB" not in RELEASE
    assert re.search(r"quay\.io/skopeo/stable:v[\d.]+@sha256:[0-9a-f]{64}", mr.SKOPEO_IMAGE)
    assert "latest" not in (ROOT / "scripts" / "mirror_release.py").read_text(encoding="utf-8").split('"""', 2)[2]


def test_the_release_only_starts_the_mirror_and_never_fails_on_it():
    publish = RELEASE[RELEASE.index("\n  publish:"):]
    step = publish[publish.index("- name: Start the Docker Hub mirror"):]
    assert 'if ! gh workflow run mirror.yml --ref main -f tag="$TAG"; then' in step and "::warning::" in step
    assert RELEASE.count("actions: write") == 1 and "actions: write" in publish


# Live: copy the real v1.1.13 API image from GHCR into a throwaway local registry and prove nothing changed.
LIVE = os.environ.get("MIRROR_LIVE_TEST") == "1"
REGISTRY_IMAGE = "registry:2@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
SOURCE = "ghcr.io/hamza-aziz-ai/medical-chatbot-api@sha256:f59d504fcb370a311e8d5023a1ec7cc07a93782fcc1dbca6fe0ffb241203a3e5"


@pytest.mark.skipif(not LIVE, reason="the live mirror test needs Docker, network access and MIRROR_LIVE_TEST=1")
def test_live_copy_preserves_the_index_its_images_attestations_and_blobs(tmp_path):
    name = f"mirror-test-{uuid.uuid4().hex[:8]}"
    docker = lambda *args: subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()
    docker("network", "create", name)
    try:
        docker("run", "-d", "--name", name, "--network", name, "-p", "127.0.0.1::5000", REGISTRY_IMAGE)
        port = docker("port", name, "5000/tcp").splitlines()[0].rsplit(":", 1)[1]
        (tmp_path / "auth.json").write_text("{}")
        (tmp_path / "local.conf").write_text(f'[[registry]]\nlocation = "{name}:5000"\ninsecure = true\n')
        skopeo = mr.Skopeo(str(tmp_path / "auth.json"), docker_args=(
            "--network", name, "-v", f"{tmp_path / 'local.conf'}:/etc/containers/registries.conf.d/local.conf:ro"))
        target = f"{name}:5000/medical-chatbot-api:1.1.13"
        assert skopeo.digest(target) is None
        mr.mirror({"api": SOURCE}, "unused", "1.1.13", _Local(skopeo, f"{name}:5000"), log=lambda line: None)
        want = SOURCE.split("@", 1)[1]
        assert skopeo.digest(target) == want
        # Every manifest in the index, the attestation manifest among them, and every blob they name.
        index = json.loads(skopeo.run("inspect", "--raw", f"docker://{target}").stdout)
        kinds = {m.get("annotations", {}).get("vnd.docker.reference.type", "image") for m in index["manifests"]}
        assert kinds == {"image", "attestation-manifest"}
        for entry in index["manifests"]:
            ref = f"{name}:5000/medical-chatbot-api@{entry['digest']}"
            assert skopeo.digest(ref) == entry["digest"]
            image = json.loads(skopeo.run("inspect", "--raw", f"docker://{ref}").stdout)
            for blob in [image["config"], *image["layers"]]:
                url = f"http://127.0.0.1:{port}/v2/medical-chatbot-api/blobs/{blob['digest']}"
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as response:
                    assert int(response.headers["Content-Length"]) == blob["size"]
        # A second run skips, and a different digest under the same tag is refused.
        mr.mirror({"api": SOURCE}, "unused", "1.1.13", _Local(skopeo, f"{name}:5000"), log=lambda line: None)
        with pytest.raises(mr.MirrorError, match="never overwritten"):
            mr.mirror({"api": SOURCE.replace(want, index["manifests"][0]["digest"])}, "unused", "1.1.13",
                      _Local(skopeo, f"{name}:5000"), log=lambda line: None)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", name], capture_output=True)


class _Local:
    """Points mirror()'s docker.io destinations at the local registry instead."""

    def __init__(self, skopeo, registry):
        self.skopeo, self.registry = skopeo, registry

    def local(self, ref):
        return re.sub(r"^docker\.io/[^/]+/", f"{self.registry}/", ref)

    def digest(self, ref):
        return self.skopeo.digest(self.local(ref))

    def copy(self, source, destination):
        self.skopeo.copy(source, self.local(destination))
