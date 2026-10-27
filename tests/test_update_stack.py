"""The local stack updater (D-021), against a fake Docker and a fake GitHub."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("update_stack", Path(__file__).resolve().parents[1] / "scripts" / "update_stack.py")
us = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(us)

COMPOSE = b"services:\n  neo4j:\n    image: neo4j:5.26@sha256:" + b"a" * 64 + b"\n"
HOSTED_COMPOSE = b"services:\n  cloudflared:\n    image: cloudflare/cloudflared@sha256:" + b"b" * 64 + b"\n"
NOISE = "SECRET-DOCKER-OUTPUT"


def image(name, n):
    return f"ghcr.io/hamza-aziz-ai/medical-chatbot-{name}@sha256:{str(n) * 64}"


def release_files(tag, n, compose=COMPOSE, evaluation=True, health=False, hosted_compose=HOSTED_COMPOSE):
    api, web = image("api", n), image("web", n)
    return {
        "compose.yaml": compose,
        "compose.hosted.yaml": hosted_compose,
        "release.env": f"API_IMAGE={api}\nWEB_IMAGE={web}\n".encode(),
        "manifest.json": json.dumps({"tag": tag, "images": {"api": api, "web": web}, "evaluation_passed": evaluation,
                                     **({"capabilities": {"health": True}} if health else {})}).encode(),
    }


class Fake:
    """Docker and GitHub: running containers, releases, and steps told to fail."""

    def __init__(self, tmp_path):
        self.calls = []
        self.fail = set()
        self.healthy = True
        self.health_route = {}  # api image -> /api/health status; images without an entry have no route (404)
        self.running = {}  # service -> image reference
        self.tunnel = False  # hosted (D-032): whether cloudflared, the only public way in, is running
        self.fail_once = set()  # steps that fail the next time only
        self.broken = set()  # api images whose page and answers fail the health check
        self.releases = {}
        self.files = {}
        self.tmp = tmp_path

    def add_release(self, tag, n, **kwargs):
        files = release_files(tag, n, **kwargs)
        base = f"{us.ASSET_URL}{tag}/"
        self.files[tag] = files
        self.releases[tag] = {"tag_name": tag, "draft": False, "prerelease": False,
                              "assets": [{"name": name, "browser_download_url": base + name} for name in files]}

    def http_get(self, url):
        if "fail_http" in self.fail:
            raise OSError("network down")
        if url.endswith("/releases/latest"):
            tag = max(self.releases, key=us.version)
            return json.dumps(self.releases[tag]).encode()
        if "/releases/tags/" in url:
            return json.dumps(self.releases[url.rsplit("/", 1)[1]]).encode()
        if url.startswith(us.ASSET_URL):
            tag, name = url[len(us.ASSET_URL):].split("/")
            return self.files[tag][name]
        if url.endswith("/api/health"):
            code = self.health_route.get(self.running.get("api"), 404)
            if code != 200:
                raise OSError(f"HTTP {code}")
            return b'{"status": "ok"}'
        healthy = self.healthy and self.running.get("api") not in self.broken
        if url.endswith("/api/?search=what+causes+asthma"):
            return json.dumps({"status": "answer" if healthy else "abstain"}).encode()
        return b'<div id="app">' if healthy else b""

    def run(self, args, env=None):
        args = list(args)
        step = self.step(args)
        self.calls.append(step)
        done = lambda out="": subprocess.CompletedProcess(args, 0, out, NOISE)  # noqa: E731
        if step in self.fail or step in self.fail_once:
            self.fail_once.discard(step)
            return subprocess.CompletedProcess(args, 1, "", NOISE)
        if step == "stop_tunnel":
            self.tunnel = False
        if step == "up_tunnel":
            # Public access must never open on a stack that is not serving the checked release.
            assert self.running and self.running.get("api") not in self.broken
            self.tunnel = True
        if args[:2] == ["docker", "ps"]:
            service = next(a.rsplit("=", 1)[1] for a in args if a.startswith("label=com.docker.compose.service="))
            return done(f"c-{service}" if service in self.running else "")
        if args[:3] == ["docker", "image", "inspect"]:
            return done(f"id:{args[-1]}")
        if args[:2] == ["docker", "inspect"] and "{{.Image}}" in args:
            return done(f"id:{self.running[args[-1][2:]]}")
        if args[:2] == ["docker", "inspect"]:
            return done(str(self.tmp / "running-compose.yaml"))
        if step == "backup":
            mount = next(a for a in args if a.endswith(":/backup"))
            name = next(a for a in args if a.startswith("/backup/")).split("/", 2)[2]
            Path(mount[: -len(":/backup")], name).write_bytes(b"archive")
        if step == "up_app":
            self.running = {"api": env["API_IMAGE"], "web": env["WEB_IMAGE"]}
        if step == "up_all":
            self.running = {"api": env["API_IMAGE"], "web": env["WEB_IMAGE"]}
        if step in ("stop_app", "stop_all"):
            self.running = {}
        if step == "port":
            return done("127.0.0.1:18080")
        return done()

    @staticmethod
    def step(args):
        joined = " ".join(args)
        if args[:2] == ["docker", "compose"]:
            tail = args[args.index("--env-file") + 2:]
            if tail[:1] == ["pull"]:
                return "pull"
            if tail == ["stop", "web", "api"]:
                return "stop_app"
            if tail == ["stop", "cloudflared"]:
                return "stop_tunnel"
            if tail[:1] == ["up"] and tail[-1] == "cloudflared":
                return "up_tunnel"
            if tail == ["stop", "neo4j"]:
                return "stop_neo4j"
            if tail == ["stop"]:
                return "stop_all"
            if "importer" in tail:
                return "import"
            if tail[:1] == ["up"] and tail[-1] == "neo4j":
                return "up_neo4j"
            if tail[:1] == ["up"] and tail[-2:] == ["api", "web"]:
                return "up_app"
            if tail[:1] == ["up"]:
                return "up_all"
            if tail[:1] == ["port"]:
                return "port"
        if "czf" in args:
            return "backup"
        if "tzf" in args:
            return "verify_backup"
        if "find /data" in joined:
            return "restore"
        return " ".join(args[:3])


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake = Fake(tmp_path)
    for name, value in {"DEPLOY": tmp_path / "deploy", "STATE": tmp_path / "deploy" / "current.json",
                        "JOURNAL": tmp_path / "deploy" / "journal.json", "FAILED": tmp_path / "deploy" / "failed.json"}.items():
        monkeypatch.setattr(us, name, value)
    monkeypatch.setattr(us, "run", fake.run)
    monkeypatch.setattr(us, "http_get", fake.http_get)
    monkeypatch.setattr(us.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(us, "setup_logging", lambda: None)
    return fake


def enrolled(fake, tag="v1.1.0", n=1, hosted=False):
    """A stack running a published release and recorded by --enroll."""
    fake.add_release(tag, n)
    deployment = us.download(fake.releases[tag], hosted)
    fake.running = {"api": deployment["api_image"], "web": deployment["web_image"]}
    fake.tunnel = hosted
    us.write_json(us.STATE, deployment)
    fake.calls.clear()
    return deployment


def steps(fake):
    return [c for c in fake.calls if not c.startswith(("docker ps", "docker inspect", "docker image", "docker info"))
            and c != "port"]


# Doing nothing when nothing should happen.

def test_the_same_release_changes_nothing(fake):
    enrolled(fake)
    assert us.update() == 0
    assert steps(fake) == []


def test_not_enrolled_or_stopped_stacks_are_left_alone(fake):
    fake.add_release("v1.1.0", 1)
    assert us.update() == 0 and steps(fake) == []
    enrolled(fake)
    fake.running = {}
    assert us.update() == 0 and steps(fake) == []


def test_docker_not_running_or_another_run_holding_the_lock_does_nothing(fake):
    fake.fail.add("docker info")
    assert us.main([]) == 0
    assert fake.calls == ["docker info"]
    held = us.locked()
    try:
        assert us.locked() is None
    finally:
        held.close()


def test_images_changed_by_hand_stop_automatic_updates(fake):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    fake.running["api"] = image("api", 9)
    assert us.update() == 0 and steps(fake) == []


def test_network_trouble_changes_nothing_and_is_retried(fake):
    enrolled(fake)
    fake.fail.add("fail_http")
    assert us.main([]) == 1
    assert steps(fake) == [] and not us.FAILED.exists()


# Refusing releases that are not safe to deploy unattended.

@pytest.mark.parametrize("change", ["digest", "manifest", "evaluation", "compose", "host"])
def test_unsafe_releases_are_refused_before_anything_changes(fake, change):
    current = enrolled(fake)
    fake.add_release("v1.1.1", 2, compose=COMPOSE + b"    volumes: ['/:/host']\n" if change == "compose" else COMPOSE,
                     evaluation=change != "evaluation")
    files, assets = fake.files["v1.1.1"], fake.releases["v1.1.1"]["assets"]
    if change == "digest":
        files["release.env"] = b"API_IMAGE=ghcr.io/someone-else/api:latest\nWEB_IMAGE=x\n"
    if change == "manifest":
        files["manifest.json"] = json.dumps({"tag": "v9.9.9", "images": {}, "evaluation_passed": True}).encode()
    if change == "host":
        assets[0]["browser_download_url"] = "https://example.com/compose.yaml"
    with pytest.raises(us.Refused):
        us.update()
    assert steps(fake) == [] and json.loads(us.STATE.read_text())["tag"] == current["tag"]


def test_older_releases_are_never_deployed(fake):
    enrolled(fake, "v1.2.0")
    fake.add_release("v1.1.5", 3)
    assert us.update() == 0 and steps(fake) == []


# Deploying, and restoring when something fails.

def test_an_update_backs_up_imports_and_records_the_new_release(fake):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    assert us.update() == 0
    assert steps(fake) == ["pull", "stop_app", "stop_neo4j", "backup", "verify_backup", "up_neo4j", "import", "up_app"]
    assert json.loads(us.STATE.read_text())["tag"] == "v1.1.1"
    assert not us.JOURNAL.exists() and fake.running["api"] == image("api", 2)


def test_a_failed_pull_leaves_the_stack_running_and_is_retried(fake):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    fake.fail.add("pull")
    with pytest.raises(us.Refused):
        us.update()
    assert steps(fake) == ["pull"] and not us.JOURNAL.exists() and not us.FAILED.exists()


def test_a_failed_backup_restarts_the_previous_release_without_restoring(fake):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    fake.fail.add("backup")
    assert us.update() == 1
    assert "restore" not in fake.calls and "import" not in fake.calls
    assert fake.running["api"] == image("api", 1)
    assert json.loads(us.STATE.read_text())["tag"] == "v1.1.0"


@pytest.mark.parametrize("failing", ["import", "up_app", "health"])
def test_a_failure_after_the_backup_restores_it_and_the_previous_release(fake, failing):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    if failing == "health":
        fake.healthy = False
        original = fake.run

        def heal_on_restore(args, env=None):
            result = original(args, env)
            if fake.calls[-1] == "restore":
                fake.healthy = True
            return result

        fake.run = heal_on_restore
        us.run = heal_on_restore
    else:
        fake.fail.add(failing)
    assert us.update() == 1
    assert fake.calls.index("restore") > fake.calls.index("backup")
    assert fake.running["api"] == image("api", 1)
    assert json.loads(us.STATE.read_text())["tag"] == "v1.1.0"
    assert json.loads(us.FAILED.read_text())["tag"] == "v1.1.1"
    fake.calls.clear()
    assert us.update() == 0 and steps(fake) == []  # the failed release is not retried


def test_a_failed_recovery_keeps_the_app_stopped_and_blocks_later_runs(fake):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    fake.fail.update({"import", "restore"})
    assert us.update() == 1
    journal = json.loads(us.JOURNAL.read_text())
    assert journal["recovery_failed"] and fake.running == {}
    fake.calls.clear()
    assert us.update() == 1 and steps(fake) == []


@pytest.mark.parametrize("phase, restores", [("prepared", False), ("stopped", False), ("backup_ready", True),
                                             ("importing", True), ("started", True)])
def test_an_interrupted_update_is_reversed_first_restoring_only_a_verified_backup(fake, phase, restores):
    current = enrolled(fake)
    fake.add_release("v1.1.1", 2)
    target = us.download(fake.releases["v1.1.1"])
    archive = us.DEPLOY / "backups" / "neo4j-data.tgz"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"archive")
    us.write_json(us.JOURNAL, {"target": target, "previous": current, "phase": phase, "backup": str(archive)})
    fake.running = {}
    fake.calls.clear()
    assert us.update() == 1
    assert ("restore" in fake.calls) == restores
    assert fake.running["api"] == image("api", 1) and not us.JOURNAL.exists()


def test_a_crash_after_recording_the_new_release_is_finished_not_reversed(fake):
    current = enrolled(fake)
    fake.add_release("v1.1.1", 2)
    target = us.download(fake.releases["v1.1.1"])
    us.write_json(us.STATE, target)
    us.write_json(us.JOURNAL, {"target": target, "previous": current, "phase": "committed", "backup": "x"})
    fake.running = {"api": target["api_image"], "web": target["web_image"]}
    assert us.update() == 0
    assert "restore" not in fake.calls and not us.JOURNAL.exists()
    assert json.loads(us.STATE.read_text())["tag"] == "v1.1.1"


def test_old_releases_and_backups_are_pruned_but_the_current_one_is_kept(fake):
    enrolled(fake)
    for i, tag in enumerate(["v1.1.1", "v1.1.2", "v1.1.3"], start=2):
        fake.add_release(tag, i)
        assert us.update() == 0
    assert sorted(p.name for p in (us.DEPLOY / "releases").iterdir()) == ["v1.1.2", "v1.1.3"]
    assert len(list((us.DEPLOY / "backups").glob("*.tgz"))) <= us.KEEP


def test_logs_hold_no_docker_output_or_probe(fake, caplog):
    enrolled(fake)
    fake.add_release("v1.1.1", 2)
    fake.fail.add("import")
    caplog.set_level("DEBUG")
    us.update()
    assert NOISE not in caplog.text and "what causes asthma" not in caplog.text and "search=" not in caplog.text


# Enrolling.

def test_enrolling_records_the_running_release_only_if_it_really_is_that_release(fake):
    fake.add_release("v1.1.0", 1)
    running_compose = fake.tmp / "running-compose.yaml"
    running_compose.write_bytes(COMPOSE)
    fake.running = {"api": image("api", 1), "web": image("web", 1)}
    assert us.enroll() == 0
    state = json.loads(us.STATE.read_text())
    assert state["tag"] == "v1.1.0" and state["compose_sha256"] == hashlib.sha256(COMPOSE).hexdigest()
    assert not any(step in fake.calls for step in ("pull", "stop_app", "import", "up_app"))

    us.STATE.unlink()
    fake.running["web"] = image("web", 7)
    with pytest.raises(us.Refused, match="images"):
        us.enroll()
    fake.running["web"] = image("web", 1)
    running_compose.write_bytes(COMPOSE + b"# edited\n")
    with pytest.raises(us.Refused, match="compose.yaml"):
        us.enroll()
    assert not us.STATE.exists()


# D-022: releases that have the /health route must pass it; older ones keep the older checks.

def test_a_release_with_the_health_route_must_report_ok(fake):
    enrolled(fake)
    fake.add_release("v1.2.0", 2, health=True)
    fake.health_route[image("api", 2)] = 200
    assert us.update() == 0
    state = json.loads(us.STATE.read_text())
    assert state["tag"] == "v1.2.0" and state["health"] is True


@pytest.mark.parametrize("code", [503, 404])
def test_a_release_whose_health_route_fails_is_rolled_back_to_one_without_it(fake, code):
    enrolled(fake)  # v1.1.0: no health route, so its own checks do not ask for one
    fake.add_release("v1.2.0", 2, health=True)
    if code == 503:
        fake.health_route[image("api", 2)] = 503
    assert us.update() == 1
    state = json.loads(us.STATE.read_text())
    assert state["tag"] == "v1.1.0" and not state.get("health")
    assert fake.running["api"] == image("api", 1)


# The hosted stack (D-032): no volume backup, public access closed while the graph changes.

def test_a_hosted_update_closes_public_access_rebuilds_the_graph_and_reopens_after_the_checks(fake):
    enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    assert us.update() == 0
    assert steps(fake) == ["pull", "stop_tunnel", "stop_app", "import", "up_app", "up_tunnel"]
    state = json.loads(us.STATE.read_text())
    assert state["tag"] == "v1.1.1" and state["mode"] == "hosted" and state["compose"].endswith("compose.hosted.yaml")
    assert fake.tunnel and fake.running["api"] == image("api", 2) and not us.JOURNAL.exists()


def test_a_hosted_site_that_is_not_healthy_is_not_updated(fake):
    enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    fake.healthy = False  # for example a paused graph
    assert us.update() == 0
    assert steps(fake) == [] and json.loads(us.STATE.read_text())["tag"] == "v1.1.0" and fake.tunnel


@pytest.mark.parametrize("failure", ["import", "checks"])
def test_a_failed_hosted_update_rebuilds_the_previous_graph_before_reopening(fake, failure):
    enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    if failure == "import":
        fake.fail_once.add("import")
    else:
        fake.broken.add(image("api", 2))
    assert us.update() == 1
    recovery = ["stop_tunnel", "stop_app", "import", "up_app", "up_tunnel"]
    assert steps(fake)[-len(recovery):] == recovery
    assert "up_tunnel" not in steps(fake)[:-1]  # opened once, for the previous release only
    assert json.loads(us.STATE.read_text())["tag"] == "v1.1.0" and json.loads(us.FAILED.read_text())["tag"] == "v1.1.1"
    assert fake.tunnel and fake.running["api"] == image("api", 1)


def test_a_failed_hosted_recovery_keeps_public_access_closed(fake):
    enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    fake.fail.add("import")
    assert us.update() == 1
    assert not fake.tunnel and "up_tunnel" not in steps(fake)
    assert json.loads(us.JOURNAL.read_text())["recovery_failed"] is True
    assert us.update() == 1 and not fake.tunnel


def test_a_crash_while_importing_is_recovered_by_rebuilding_the_previous_graph(fake):
    previous = enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    target = us.download(fake.releases["v1.1.1"], True)
    us.write_json(us.JOURNAL, {"target": target, "previous": previous, "phase": "importing"})
    fake.running, fake.tunnel = {}, False
    fake.calls.clear()
    assert us.update() == 1
    assert steps(fake) == ["stop_tunnel", "stop_app", "import", "up_app", "up_tunnel"]
    assert fake.running["api"] == image("api", 1) and fake.tunnel


def test_a_crash_before_the_import_reopens_without_touching_the_graph(fake):
    previous = enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2)
    target = us.download(fake.releases["v1.1.1"], True)
    us.write_json(us.JOURNAL, {"target": target, "previous": previous, "phase": "closed"})
    fake.calls.clear()
    us.update()
    assert "import" not in steps(fake) and fake.tunnel


def test_a_hosted_release_that_changes_its_compose_file_needs_a_manual_deploy(fake):
    enrolled(fake, hosted=True)
    fake.add_release("v1.1.1", 2, hosted_compose=HOSTED_COMPOSE + b"    ports: ['0.0.0.0:80:8080']\n")
    with pytest.raises(us.Refused, match="compose.hosted.yaml"):
        us.update()
    assert steps(fake) == []


def test_enrolling_the_hosted_stack_checks_it_runs_the_released_hosted_compose(fake):
    fake.add_release("v1.1.0", 1)
    running_compose = fake.tmp / "running-compose.yaml"
    fake.running = {"api": image("api", 1), "web": image("web", 1)}
    running_compose.write_bytes(COMPOSE)
    with pytest.raises(us.Refused, match="compose.hosted.yaml"):
        us.enroll(hosted_stack=True)
    running_compose.write_bytes(HOSTED_COMPOSE)
    assert us.enroll(hosted_stack=True) == 0
    assert json.loads(us.STATE.read_text())["mode"] == "hosted"
