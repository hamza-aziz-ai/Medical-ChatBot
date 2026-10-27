"""Docker Hub repository metadata (D-031): the committed files are valid, and the sync changes only what differs."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dockerhub_metadata", ROOT / "scripts" / "dockerhub_metadata.py")
dm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dm)


def test_the_committed_metadata_fits_docker_hubs_limits():
    wanted = dm.desired()
    assert set(wanted) == {"medical-chatbot-api", "medical-chatbot-web"}
    for want in wanted.values():
        assert 0 < len(want["description"].encode()) <= 100
        assert "not medical advice" in want["full_description"]
        assert want["immutable_tags_settings"]["enabled"] is True


def test_too_long_descriptions_are_refused(tmp_path):
    (tmp_path / "overview.md").write_text("x")
    (tmp_path / "r.json").write_text(json.dumps({"overview": "overview.md", "immutable_tags_rules": ["x"], "repositories": {"a": "y" * 101}}))
    with pytest.raises(dm.HubError):
        dm.desired(tmp_path / "r.json")


WANT = {"description": "d", "full_description": "overview", "immutable_tags_settings": {"enabled": True, "rules": ["r"]}}


class FakeHub:
    def __init__(self, current, apply=True):
        self.current, self.apply, self.calls = dict(current), apply, []

    def __call__(self, method, path, body=None, token=None):
        self.calls.append((method, path))
        assert token == "t"
        if method == "PATCH" and self.apply:
            if path.endswith("/immutabletags"):
                self.current["immutable_tags_settings"] = {"enabled": body["immutable_tags"], "rules": body["immutable_tags_rules"]}
            else:
                self.current.update(body)
        return dict(self.current)


def sync(hub):
    dm.sync("ns", {"repo": WANT}, "t", call=hub, log=lambda line: None)


def test_a_matching_repository_is_only_read():
    hub = FakeHub({**WANT, "full_description": "overview\n"})
    sync(hub)
    assert hub.calls == [("GET", "/v2/namespaces/ns/repositories/repo")]


def test_differences_are_patched_and_read_back():
    hub = FakeHub({"description": "old", "full_description": "", "immutable_tags_settings": {"enabled": False, "rules": [".*"]}})
    sync(hub)
    assert [c[0] for c in hub.calls] == ["GET", "PATCH", "PATCH", "GET"]
    assert ("PATCH", "/v2/repositories/ns/repo") in hub.calls
    assert ("PATCH", "/v2/namespaces/ns/repositories/repo/immutabletags") in hub.calls


def test_a_change_that_does_not_take_effect_fails():
    with pytest.raises(dm.HubError, match="still differs"):
        sync(FakeHub({**WANT, "description": "old"}, apply=False))


def test_the_workflow_reads_only_the_token_it_needs():
    workflow = (ROOT / ".github" / "workflows" / "dockerhub-metadata.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow and "write" not in workflow
    assert "secrets.DOCKERHUB_TOKEN" in workflow and workflow.count("secrets.") == 1
