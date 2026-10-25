"""Release planning for autorelease.yml (D-019): when to release, which version, and when to stop."""
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("next_release", Path(__file__).resolve().parents[1] / "scripts" / "next_release.py")
nr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nr)

HEAD = "abc123"


def published(*tags):
    return [{"tag_name": tag, "draft": False} for tag in tags]


def images(states):
    return lambda number: states.get(number, nr.ABSENT)


def changed(*paths):
    return lambda base: list(paths)


def run_plan(tags, releases, image_states=None, level="patch", changes=changed("api/main.py"), all_tags=()):
    return nr.plan(HEAD, tags, releases, images(image_states or {}), level, changes, all_tags)


# Planning on given states.

def test_a_shipped_change_after_a_published_release_gets_the_next_version():
    assert run_plan(["v1.0.0"], published("v1.0.0")) == ("v1.0.1", HEAD)
    assert run_plan(["v1.0.0"], published("v1.0.0"), level="minor") == ("v1.1.0", HEAD)
    assert run_plan(["v1.9.3"], published("v1.9.3"), level="major") == ("v2.0.0", HEAD)


def test_nothing_shipped_changed_means_no_release():
    assert run_plan(["v1.0.0"], published("v1.0.0"), changes=changed()) is None


def test_a_draft_release_stops_the_run():
    with pytest.raises(nr.Stop, match="draft"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0") + [{"tag_name": "v1.1.0", "draft": True}])


def test_an_unused_abandoned_tag_is_skipped_and_never_reused():
    seen = []
    result = run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"), changes=lambda base: seen.append(base) or ["api/x"])
    assert result == ("v1.1.1", HEAD)
    assert seen == ["v1.0.0"]


def test_version_images_without_a_release_stop_until_a_newer_version_is_published_by_hand():
    stuck = {"1.1.0": nr.PRESENT}
    with pytest.raises(nr.Stop, match="next unused version"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"), stuck)
    # The owner publishes v1.1.1 through release.yml; automation resumes from it.
    assert run_plan(["v1.1.1", "v1.1.0", "v1.0.0"], published("v1.0.0", "v1.1.1"), stuck) == ("v1.1.2", HEAD)


def test_failed_lookups_stop_instead_of_reading_as_absent():
    with pytest.raises(nr.Stop, match="list releases"):
        run_plan(["v1.0.0"], None)
    with pytest.raises(nr.Stop, match="check the images"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"), {"1.1.0": nr.ERROR})


def test_a_version_that_exists_off_main_is_never_reused():
    with pytest.raises(nr.Stop, match="already exists"):
        run_plan(["v1.0.0"], published("v1.0.0"), all_tags={"v1.0.0", "v1.0.1"})


def test_shipped_paths():
    for path in ["api/main.py", "api/dictionary/entities.json", "frontend/src/App.vue", "docker/api.Dockerfile",
                 "compose.yaml", "requirements.txt", "requirements-deploy.txt", ".env.example"]:
        assert nr.is_shipped(path), path
    for path in ["docs/FLOW.md", "README.md", "eval/cases.jsonl", "tests/test_api.py", "scripts/compose_smoke.sh",
                 ".github/workflows/release.yml", "api/models/model1.json", "api/data/questions.json",
                 "frontend/tests/App.spec.js", "frontend/README.md", "requirements-dev.txt"]:
        assert not nr.is_shipped(path), path


# Git history, on a throwaway repository.

@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def run(*args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("config", "commit.gpgsign", "false")

    def commit(path, text):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        run("add", path)
        run("commit", "-q", "-m", f"change {path}")
        return run("rev-parse", "HEAD")

    return SimpleNamespace(run=run, commit=commit)


def test_tags_sort_numerically_and_only_main_counts(repo):
    repo.commit("api/main.py", "1")
    for tag in ["v1.9.0", "v1.10.0", "v1.2.0", "not-a-version", "v2.0.0-rc1"]:
        repo.run("tag", tag)
    repo.run("checkout", "-q", "-b", "side")
    repo.commit("api/main.py", "side")
    repo.run("tag", "v9.0.0")
    repo.run("checkout", "-q", "main")
    assert nr.tags_on("main") == ["v1.10.0", "v1.9.0", "v1.2.0"]


def test_docs_only_and_reverted_changes_ship_nothing(repo):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    repo.commit("docs/FLOW.md", "docs")
    assert nr.shipped_changes("v1.0.0", "main") == []
    repo.commit("api/main.py", "2")
    assert nr.shipped_changes("v1.0.0", "main") == ["api/main.py"]
    repo.commit("api/main.py", "1")
    assert nr.shipped_changes("v1.0.0", "main") == []


def test_main_moving_on_is_released_from_the_head_seen(repo, monkeypatch, capsys):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    repo.commit("frontend/src/App.vue", "2")
    head = repo.run("rev-parse", "HEAD")
    monkeypatch.setattr(nr, "list_releases", lambda repo_name: published("v1.0.0"))
    monkeypatch.setattr(nr, "image_lookup", lambda prefix: images({}))
    monkeypatch.setattr(nr, "label_bump", lambda *args: "patch")
    assert nr.main(["--repo", "o/r", "--image-prefix", "ghcr.io/o/x", "--ref", "main"]) == 0
    assert capsys.readouterr().out.splitlines() == ["release=true", "tag=v1.0.1", f"sha={head}"]
    repo.commit("api/main.py", "3")  # main moves on: the next run sees the new head
    assert nr.main(["--repo", "o/r", "--image-prefix", "ghcr.io/o/x", "--ref", "main"]) == 0
    assert capsys.readouterr().out.splitlines()[2] == f"sha={repo.run('rev-parse', 'HEAD')}"


# Lookup adapters: only a confirmed "not found" counts as absent.

def fake_run(returncode, stdout="", stderr=""):
    return lambda *args, **kwargs: subprocess.CompletedProcess(args, returncode, stdout, stderr)


@pytest.mark.parametrize("returncode, stderr, expected", [
    (0, "", nr.PRESENT),
    (1, "ERROR: ghcr.io/o/x-api:1.1.0: not found", nr.ABSENT),
    (1, "ERROR: unexpected status from HEAD request: 401 Unauthorized", nr.ERROR),
    (1, "ERROR: failed to do request: dial tcp: lookup ghcr.io: no such host", nr.ERROR),
    (1, "ERROR: unexpected status: 429 Too Many Requests", nr.ERROR),
])
def test_image_lookup_tells_absence_from_failure(monkeypatch, returncode, stderr, expected):
    monkeypatch.setattr(nr.subprocess, "run", fake_run(returncode, stderr=stderr))
    assert nr.image_lookup("ghcr.io/o/x")("1.1.0") == expected


def test_release_listing_failure_is_not_an_empty_list(monkeypatch):
    monkeypatch.setattr(nr.subprocess, "run", fake_run(1, stderr="HTTP 401: Bad credentials"))
    assert nr.list_releases("o/r") is None
    monkeypatch.setattr(nr.subprocess, "run", fake_run(0, stdout='{"tag_name":"v1.0.0","draft":false}\n'))
    assert nr.list_releases("o/r") == published("v1.0.0")


def test_labels_pick_the_highest_bump_and_failures_stop(repo, monkeypatch):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    for branch in ["a", "b"]:
        repo.run("checkout", "-q", "-b", branch)
        repo.commit(f"api/{branch}.py", branch)
        repo.run("checkout", "-q", "main")
        repo.run("merge", "-q", "--no-ff", "-m", f"Merge pull request from {branch}", branch)
    labels = iter(["release:minor\nbug", "release:major"])
    real_run = subprocess.run

    def gh_or_git(args, **kwargs):
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, next(labels), "")
        return real_run(args, **kwargs)

    monkeypatch.setattr(nr.subprocess, "run", gh_or_git)
    assert nr.label_bump("o/r", "v1.0.0", "main") == "major"

    def failing(args, **kwargs):
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 1, "", "HTTP 403: rate limit exceeded")
        return real_run(args, **kwargs)

    monkeypatch.setattr(nr.subprocess, "run", failing)
    with pytest.raises(nr.Stop, match="labels"):
        nr.label_bump("o/r", "v1.0.0", "main")
