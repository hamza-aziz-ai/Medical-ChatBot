"""Release planning for autorelease.yml (D-019): one release per merge, in merge order, and when to stop."""
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("next_release", Path(__file__).resolve().parents[1] / "scripts" / "next_release.py")
nr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nr)


def published(*tags):
    return [{"tag_name": tag, "draft": False} for tag in tags]


def images(states):
    return lambda number: states.get(number, nr.ABSENT)


def run_plan(tags, releases, image_states=None, pending=("m1", "m2"), levels=None, all_tags=(), require=None):
    seen = []

    def pending_after(baseline):
        seen.append(baseline)
        return list(pending)

    result = nr.plan(tags, releases, images(image_states or {}), pending_after,
                     lambda sha: (levels or {}).get(sha, "patch"), all_tags, require)
    return result, seen


# Planning on given states.

def test_the_oldest_unreleased_merge_gets_the_next_version():
    assert run_plan(["v1.0.0"], published("v1.0.0"))[0] == ("v1.0.1", "m1")
    assert run_plan(["v1.0.0"], published("v1.0.0"), levels={"m1": "minor"})[0] == ("v1.1.0", "m1")
    assert run_plan(["v1.9.3"], published("v1.9.3"), levels={"m1": "major"})[0] == ("v2.0.0", "m1")


def test_nothing_left_to_release_ends_the_chain():
    assert run_plan(["v1.0.0"], published("v1.0.0"), pending=())[0] is None


def test_a_draft_release_stops_the_run():
    with pytest.raises(nr.Stop, match="draft"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0") + [{"tag_name": "v1.1.0", "draft": True}])


def test_an_abandoned_tag_keeps_its_number_reserved():
    result, seen = run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"))
    assert result == ("v1.1.1", "m1")
    assert seen == ["v1.0.0"]


def test_version_images_without_a_release_stop_until_a_newer_version_is_published_by_hand():
    stuck = {"1.1.0": nr.PRESENT}
    with pytest.raises(nr.Stop, match="next unused version"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"), stuck)
    # The owner publishes v1.1.1 through release.yml; automation resumes from it.
    result, seen = run_plan(["v1.1.1", "v1.1.0", "v1.0.0"], published("v1.0.0", "v1.1.1"), stuck)
    assert result == ("v1.1.2", "m1") and seen == ["v1.1.1"]


def test_failed_lookups_stop_instead_of_reading_as_absent():
    with pytest.raises(nr.Stop, match="list releases"):
        run_plan(["v1.0.0"], None)
    with pytest.raises(nr.Stop, match="check the images"):
        run_plan(["v1.1.0", "v1.0.0"], published("v1.0.0"), {"1.1.0": nr.ERROR})


def test_a_version_that_exists_off_main_is_never_reused():
    with pytest.raises(nr.Stop, match="already exists"):
        run_plan(["v1.0.0"], published("v1.0.0"), all_tags={"v1.0.0", "v1.0.1"})


def test_the_backlog_before_the_bootstrap_release_is_not_drained():
    with pytest.raises(nr.Stop, match="Publish v1.1.0"):
        run_plan(["v1.0.0"], published("v1.0.0"), require="v1.1.0")
    assert run_plan(["v1.1.0"], published("v1.1.0"), require="v1.1.0")[0] == ("v1.1.1", "m1")


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

    def merge(branch, path, text):
        """A pull request: a branch with one commit, merged with a merge commit like automerge does."""
        run("checkout", "-q", "-b", branch)
        commit(path, text)
        run("checkout", "-q", "main")
        run("merge", "-q", "--no-ff", "-m", f"Merge pull request from {branch}", branch)
        return run("rev-parse", "HEAD")

    return SimpleNamespace(run=run, commit=commit, merge=merge)


def test_tags_sort_numerically_and_only_main_counts(repo):
    repo.commit("api/main.py", "1")
    for tag in ["v1.9.0", "v1.10.0", "v1.2.0", "not-a-version", "v2.0.0-rc1"]:
        repo.run("tag", tag)
    repo.run("checkout", "-q", "-b", "side")
    repo.commit("api/main.py", "side")
    repo.run("tag", "v9.0.0")
    repo.run("checkout", "-q", "main")
    assert nr.tags_on("main") == ["v1.10.0", "v1.9.0", "v1.2.0"]


def test_each_shippable_merge_is_pending_in_order_and_docs_or_side_commits_are_not(repo):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    first = repo.merge("a", "api/a.py", "a")
    repo.merge("docs", "docs/FLOW.md", "docs")
    direct = repo.commit("frontend/src/App.vue", "direct")
    third = repo.merge("b", "api/b.py", "b")
    repo.run("checkout", "-q", "-b", "unmerged")
    repo.commit("api/c.py", "c")
    repo.run("checkout", "-q", "main")
    assert nr.unreleased("v1.0.0", "main", set()) == [first, direct, third]
    assert nr.unreleased("v1.0.0", "main", {first}) == [direct, third]


def test_a_change_and_its_revert_are_two_releases(repo):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    change = repo.merge("change", "api/main.py", "2")
    revert = repo.merge("revert", "api/main.py", "1")
    assert nr.unreleased("v1.0.0", "main", set()) == [change, revert]


def test_runs_release_one_merge_each_until_none_is_left(repo, monkeypatch, capsys):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    first = repo.merge("a", "api/a.py", "a")
    second = repo.merge("b", "api/b.py", "b")
    releases = published("v1.0.0")
    monkeypatch.setattr(nr, "list_releases", lambda repo_name: releases)
    monkeypatch.setattr(nr, "image_lookup", lambda prefix: images({}))
    monkeypatch.setattr(nr, "label_bump", lambda repo_name, sha: "minor" if sha == second else "patch")
    args = ["--repo", "o/r", "--image-prefix", "ghcr.io/o/x", "--ref", "main"]

    for expected_tag, expected_sha in [("v1.0.1", first), ("v1.1.0", second)]:
        assert nr.main(args) == 0
        assert capsys.readouterr().out.splitlines() == ["release=true", f"tag={expected_tag}", f"sha={expected_sha}"]
        # release.yml publishes it: the tag appears with a published release.
        repo.run("tag", expected_tag, expected_sha)
        releases.append({"tag_name": expected_tag, "draft": False})

    assert nr.main(args) == 0
    assert capsys.readouterr().out.splitlines() == ["release=false"]


def test_a_merge_under_an_abandoned_tag_is_released_again_under_the_next_version(repo, monkeypatch, capsys):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    merge = repo.merge("a", "api/a.py", "a")
    repo.run("tag", "v1.0.1", merge)  # the run died after creating the tag; no release, no images
    monkeypatch.setattr(nr, "list_releases", lambda repo_name: published("v1.0.0"))
    monkeypatch.setattr(nr, "image_lookup", lambda prefix: images({}))
    monkeypatch.setattr(nr, "label_bump", lambda repo_name, sha: "patch")
    assert nr.main(["--repo", "o/r", "--image-prefix", "ghcr.io/o/x", "--ref", "main"]) == 0
    assert capsys.readouterr().out.splitlines() == ["release=true", "tag=v1.0.2", f"sha={merge}"]


def test_the_bump_input_applies_to_this_run_only(repo, monkeypatch, capsys):
    repo.commit("api/main.py", "1")
    repo.run("tag", "v1.0.0")
    merge = repo.merge("a", "api/a.py", "a")
    monkeypatch.setattr(nr, "list_releases", lambda repo_name: published("v1.0.0"))
    monkeypatch.setattr(nr, "image_lookup", lambda prefix: images({}))
    monkeypatch.setattr(nr, "label_bump", lambda repo_name, sha: pytest.fail("labels are not read when bump is given"))
    assert nr.main(["--repo", "o/r", "--image-prefix", "ghcr.io/o/x", "--ref", "main", "--bump", "minor"]) == 0
    assert capsys.readouterr().out.splitlines() == ["release=true", "tag=v1.1.0", f"sha={merge}"]


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


def test_a_merge_takes_its_own_pull_request_label_and_failures_stop(monkeypatch):
    monkeypatch.setattr(nr.subprocess, "run", fake_run(0, stdout="bug\nrelease:minor\nrelease:major\n"))
    assert nr.label_bump("o/r", "abc") == "major"
    monkeypatch.setattr(nr.subprocess, "run", fake_run(0, stdout=""))
    assert nr.label_bump("o/r", "abc") == "patch"
    monkeypatch.setattr(nr.subprocess, "run", fake_run(1, stderr="HTTP 403: rate limit exceeded"))
    with pytest.raises(nr.Stop, match="labels"):
        nr.label_bump("o/r", "abc")
