"""Update the local Docker Compose stack to the latest published release, and roll back on failure (D-021).

Run every 15 minutes by a Windows scheduled task while the owner is signed in (docs/guides/DOCKER.md). Each run:
finish or reverse an interrupted update; check the latest release of this repository; and, if it is newer
than the recorded one, deploy it in a short maintenance window: pull, stop, back up the graph volume, start
Neo4j, re-import, start api and web, check health, record. Any failure restores the previous release.

One-time setup: run a published release by hand, then `python scripts/update_stack.py --enroll` records it.
Hosted mode (D-032, `--enroll --hosted`, run by a systemd timer on the VM): the graph lives on Neo4j Aura, so there is
no volume to back up. It uses the release's compose.hosted.yaml, closes public access (stops cloudflared) before
touching the graph, rebuilds the graph with the importer, and reopens only after the checks pass. Recovery rebuilds
the graph with the previous release's image, which stays on the VM.
State lives in deploy/ (git-ignored). The owner's .env is passed to Compose by path and never read here.
Logs hold steps and outcomes only: never Docker's output, the probe question, or the replies.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from app_logging import setup_logging  # noqa: E402

logger = logging.getLogger("update_stack")

REPO = "hamza-aziz-ai/Medical-ChatBot"
API_URL = f"https://api.github.com/repos/{REPO}/releases"
ASSET_URL = f"https://github.com/{REPO}/releases/download/"
PROJECT = "medical-chatbot"
VOLUME = f"{PROJECT}_neo4j-data"
ASSETS = ("compose.yaml", "release.env", "manifest.json")
HOSTED_COMPOSE = "compose.hosted.yaml"
VERSION_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
IMAGE = {name: re.compile(rf"^ghcr\.io/hamza-aziz-ai/medical-chatbot-{name}@sha256:[0-9a-f]{{64}}$") for name in ("api", "web")}
KEEP = 2  # release folders and backups kept besides those still referenced

DEPLOY = ROOT / "deploy"
STATE = DEPLOY / "current.json"
JOURNAL = DEPLOY / "journal.json"
FAILED = DEPLOY / "failed.json"

# Journal phases, in order. A backup exists only from backup_ready on, so only then may recovery restore it.
PHASES = ("prepared", "stopped", "backup_ready", "importing", "started", "committed")
# Hosted phases (D-032). From importing on, the graph's state is unknown and recovery must rebuild it.
HOSTED_PHASES = ("prepared", "closed", "importing", "started", "committed")


class Refused(Exception):
    """Nothing was changed; the message says why."""


# Plumbing, replaced by fakes in tests.

def run(args, env=None):
    """Run a command hidden, without logging its output (it may contain the question or settings)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, capture_output=True, text=True, env=env, creationflags=flags)


def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "medical-chatbot-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def ok(args, env=None):
    return run(args, env).returncode == 0


def output(args):
    result = run(args)
    return result.stdout.strip() if result.returncode == 0 else None


# State files: each written to a temporary file, then swapped in, so a crash never leaves half a file.

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(temp, path)


def set_phase(journal, phase):
    journal["phase"] = phase
    write_json(JOURNAL, journal)
    logger.info("Update to %s: %s", journal["target"]["tag"], phase)


# Releases.

def version(tag):
    return tuple(int(part) for part in VERSION_TAG.match(tag).groups())


def fetch_release(tag=None):
    data = json.loads(http_get(f"{API_URL}/tags/{tag}" if tag else f"{API_URL}/latest"))
    if data.get("draft") or data.get("prerelease") or not VERSION_TAG.match(str(data.get("tag_name", ""))):
        raise Refused("The release is not a published vX.Y.Z version.")
    return data


def parse_env(text):
    """release.env as data, never as a script."""
    values = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep:
            values[key] = value
    return values


def download(release, hosted_stack=False):
    """The release's compose file (compose.hosted.yaml for the hosted stack), release.env and manifest.json,
    checked; returns its deployment record."""
    tag = release["tag_name"]
    urls = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    folder = DEPLOY / "releases" / tag
    folder.mkdir(parents=True, exist_ok=True)
    compose_name = HOSTED_COMPOSE if hosted_stack else "compose.yaml"
    for name in (compose_name, *ASSETS[1:]):
        url = urls.get(name, "")
        if not url.startswith(f"{ASSET_URL}{tag}/"):
            raise Refused(f"The release has no {name} from this repository.")
        (folder / name).write_bytes(http_get(url))

    images = parse_env((folder / "release.env").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    api, web = images.get("API_IMAGE", ""), images.get("WEB_IMAGE", "")
    if not (IMAGE["api"].match(api) and IMAGE["web"].match(web)):
        raise Refused("release.env does not name both images by digest.")
    if manifest.get("tag") != tag or manifest.get("images") != {"api": api, "web": web}:
        raise Refused("manifest.json does not match the release and its images.")
    if manifest.get("evaluation_passed") is not True:
        raise Refused("The release's evaluation did not pass.")
    compose = folder / compose_name
    # Releases with the /health route (D-022) say so; older records lack the flag and keep the older checks,
    # so rolling back to them still works.
    health = (manifest.get("capabilities") or {}).get("health") is True
    return {"tag": tag, "api_image": api, "web_image": web, "compose": str(compose),
            "compose_sha256": hashlib.sha256(compose.read_bytes()).hexdigest(), "health": health,
            "mode": "hosted" if hosted_stack else "local"}


def hosted(deployment):
    return deployment.get("mode") == "hosted"


# Docker.

def compose_run(deployment, *args):
    """docker compose for this project with the deployment's compose file and images; .env passed by path only."""
    env = {**os.environ, "API_IMAGE": deployment["api_image"], "WEB_IMAGE": deployment["web_image"]}
    return run(["docker", "compose", "-p", PROJECT, "-f", deployment["compose"], "--project-directory", str(ROOT),
                "--env-file", str(ROOT / ".env"), *args], env)


def compose(deployment, *args):
    return compose_run(deployment, *args).returncode == 0


def container(service, running_only=True):
    args = ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}",
            "--filter", f"label=com.docker.compose.service={service}"]
    if running_only:
        args += ["--filter", "status=running"]
    found = output(args)
    return found.split()[0] if found else None


def running_matches(deployment):
    """True if the running api and web containers use exactly the deployment's images."""
    for service in ("api", "web"):
        cid = container(service)
        expected = output(["docker", "image", "inspect", "--format", "{{.Id}}", deployment[f"{service}_image"]])
        if not cid or not expected or output(["docker", "inspect", "--format", "{{.Image}}", cid]) != expected:
            return False
    return True


def neo4j_image(deployment):
    found = re.search(r"^\s*image:\s*(neo4j:\S+)\s*$", Path(deployment["compose"]).read_text(encoding="utf-8"), re.MULTILINE)
    if not found:
        raise Refused("The compose file names no Neo4j image.")
    return found.group(1)


def backup(deployment):
    """An offline archive of the graph volume, taken with the stack's own Neo4j image and then listed to check it."""
    folder = DEPLOY / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"neo4j-data-{datetime.now():%Y%m%d-%H%M%S}.tgz"
    mounts = ["-v", f"{VOLUME}:/data:ro", "-v", f"{folder}:/backup"]
    image = neo4j_image(deployment)
    made = ok(["docker", "run", "--rm", *mounts, "--entrypoint", "tar", image, "czf", f"/backup/{name}", "-C", "/data", "."])
    listed = made and ok(["docker", "run", "--rm", *mounts, "--entrypoint", "tar", image, "tzf", f"/backup/{name}"])
    return str(folder / name) if listed and (folder / name).stat().st_size > 0 else None


def restore(deployment, archive):
    archive = Path(archive)
    script = f"find /data -mindepth 1 -delete && tar xzpf /backup/{archive.name} -C /data"
    return ok(["docker", "run", "--rm", "-v", f"{VOLUME}:/data", "-v", f"{archive.parent}:/backup",
               "--entrypoint", "sh", neo4j_image(deployment), "-c", script])


def healthy(deployment, attempts=30, pause=2):
    """The page loads, a fixed question gets an answer and, for releases that have it, /api/health says ok.
    Neither the URL nor the replies are logged."""
    for _ in range(attempts):
        result = compose_run(deployment, "port", "web", "8080")
        port = result.stdout.strip() if result.returncode == 0 else ""
        if port:
            base = f"http://{port.strip().replace('0.0.0.0', '127.0.0.1')}"
            try:
                page = http_get(f"{base}/").decode("utf-8", "replace")
                reply = json.loads(http_get(f"{base}/api/?search=what+causes+asthma"))
                # A 503 or 404 raises, so a release that claims the route but lacks it never passes.
                ready = not deployment.get("health") or json.loads(http_get(f"{base}/api/health")).get("status") == "ok"
                if '<div id="app">' in page and reply.get("status") == "answer" and ready:
                    return True
            except (OSError, ValueError):
                pass
        time.sleep(pause)
    return False


# Updating and recovering.

def deploy(target, previous):
    """Move from previous to target, journaled so that any failure or crash can be reversed."""
    if not compose(target, "pull", "api", "web"):
        raise Refused("Could not pull the new images; the stack was not touched.")
    journal = {"target": target, "previous": previous}
    set_phase(journal, "prepared")
    try:
        steps_ok = (maintenance_hosted if hosted(target) else maintenance)(journal, target)
    except (OSError, ValueError, Refused):
        steps_ok = False
    if not steps_ok:
        logger.error("Update to %s failed at %s; restoring %s", target["tag"], journal["phase"], previous["tag"])
        return recover(journal)
    set_phase(journal, "committed")
    write_json(STATE, target)
    JOURNAL.unlink()
    logger.info("Updated to %s", target["tag"])
    prune()
    return True


def maintenance(journal, target):
    """The steps that change the stack, each recorded in the journal before the next starts."""
    if not (compose(target, "stop", "web", "api") and compose(target, "stop", "neo4j")):
        return False
    set_phase(journal, "stopped")
    journal["backup"] = backup(target)
    if not journal["backup"]:
        return False
    set_phase(journal, "backup_ready")
    if not compose(target, "up", "-d", "--no-build", "--pull", "never", "--wait", "neo4j"):
        return False
    set_phase(journal, "importing")
    if not (compose(target, "--profile", "init", "run", "--rm", "--no-deps", "importer")
            and compose(target, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "api", "web")):
        return False
    set_phase(journal, "started")
    return healthy(target)


def maintenance_hosted(journal, target):
    """Hosted steps (D-032): public access closes before the graph changes and reopens only after the checks pass."""
    if not (compose(target, "stop", "cloudflared") and compose(target, "stop", "web", "api")):
        return False
    set_phase(journal, "closed")
    set_phase(journal, "importing")
    if not (compose(target, "--profile", "init", "run", "--rm", "--no-deps", "importer")
            and compose(target, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "api", "web")):
        return False
    set_phase(journal, "started")
    return healthy(target) and compose(target, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "cloudflared")


def finished(journal):
    """True if a committed update is in place and healthy, so recovery only clears the journal."""
    target = journal["target"]
    if journal["phase"] != "committed" or (read_json(STATE) or {}).get("tag") != target["tag"]:
        return False
    if not (running_matches(target) and healthy(target)):
        return False
    JOURNAL.unlink()
    logger.info("Finished the update to %s", target["tag"])
    return True


def give_up(journal, previous):
    journal["recovery_failed"] = True
    write_json(JOURNAL, journal)
    logger.error("Could not restore %s; the app is stopped. See docs/ROLLBACK.md", previous["tag"])
    return False


def restored(journal, previous, target):
    write_json(STATE, previous)
    write_json(FAILED, {"tag": target["tag"]})
    JOURNAL.unlink()
    logger.warning("Restored %s; %s will not be retried automatically", previous["tag"], target["tag"])
    return False


def recover(journal):
    """Finish a committed update, or bring back the previous release; restore the backup only if one was verified."""
    if hosted(journal["target"]):
        return recover_hosted(journal)
    target, previous, phase = journal["target"], journal["previous"], journal["phase"]
    if finished(journal):
        return True

    restored_ok = True
    if PHASES.index(phase) >= PHASES.index("backup_ready"):
        restored_ok = compose(previous, "stop") and restore(previous, journal["backup"])
    back = restored_ok and compose(previous, "up", "-d", "--no-build", "--pull", "never") and healthy(previous)
    if not back:
        compose(previous, "stop", "web", "api")
        return give_up(journal, previous)
    return restored(journal, previous, target)


def recover_hosted(journal):
    """Bring back the previous release with public access closed: rebuild the graph with its image if an import
    began (a failed import leaves the graph's state unknown), and reopen only after its checks pass."""
    target, previous, phase = journal["target"], journal["previous"], journal["phase"]
    if finished(journal):
        return True
    back = compose(previous, "stop", "cloudflared") and compose(previous, "stop", "web", "api")
    if back and HOSTED_PHASES.index(phase) >= HOSTED_PHASES.index("importing"):
        back = compose(previous, "--profile", "init", "run", "--rm", "--no-deps", "importer")
    back = (back and compose(previous, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "api", "web")
            and healthy(previous)
            and compose(previous, "up", "-d", "--no-build", "--no-deps", "--pull", "never", "cloudflared"))
    if not back:
        # Public access stays closed: never serve a graph that was not checked.
        compose(previous, "stop", "cloudflared")
        compose(previous, "stop", "web", "api")
        return give_up(journal, previous)
    return restored(journal, previous, target)


def prune():
    """Keep what current.json or a journal refers to, plus the newest KEEP release folders and backups."""
    keep = {Path(STATE.parent / "releases" / read_json(STATE)["tag"])}
    for folder, pattern in ((DEPLOY / "releases", "v*"), (DEPLOY / "backups", "*.tgz")):
        items = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
        for item in items[KEEP:]:
            if item not in keep:
                if item.is_dir():
                    for child in item.iterdir():
                        child.unlink()
                    item.rmdir()
                else:
                    item.unlink()


def update():
    """One scheduled run. Returns the process exit code."""
    journal = read_json(JOURNAL)
    if journal:
        if journal.get("recovery_failed"):
            logger.error("A failed recovery needs the owner (docs/ROLLBACK.md); not updating")
            return 1
        logger.warning("Found an interrupted update to %s at %s", journal["target"]["tag"], journal["phase"])
        return 0 if recover(journal) else 1

    current = read_json(STATE)
    if not current:
        logger.info("Not enrolled; run update_stack.py --enroll once")
        return 0
    if not container("api"):
        logger.info("The stack is not running; nothing to update")
        return 0
    if not running_matches(current):
        logger.warning("The running images differ from %s; not updating", current["tag"])
        return 0

    release = fetch_release()
    tag = release["tag_name"]
    if version(tag) <= version(current["tag"]):
        return 0
    if (read_json(FAILED) or {}).get("tag") == tag:
        logger.info("%s failed before and is not retried automatically", tag)
        return 0
    target = download(release, hosted(current))
    if target["compose_sha256"] != current["compose_sha256"]:
        raise Refused(f"{tag} changes {Path(target['compose']).name}; review it, deploy it by hand and enrol again")
    # Hosted (D-032): with the graph paused or unreachable the rebuild would fail, so wait for it instead.
    if hosted(current) and not healthy(current, attempts=3):
        logger.warning("The running site is not healthy (graph paused or unreachable?); not updating to %s yet", tag)
        return 0
    logger.info("Updating from %s to %s", current["tag"], tag)
    return 0 if deploy(target, current) else 1


def enroll(tag=None, hosted_stack=False):
    """Record the running stack as a known published release, after checking it really is that release."""
    if read_json(JOURNAL):
        raise Refused("An update is in progress or needs recovery.")
    target = download(fetch_release(tag), hosted_stack)
    for service in ("api", "web"):
        output(["docker", "pull", "-q", target[f"{service}_image"]])
    if not running_matches(target):
        raise Refused(f"The running api and web are not {target['tag']}'s images.")
    cid = container("api")
    files = output(["docker", "inspect", "--format", '{{index .Config.Labels "com.docker.compose.project.config_files"}}', cid])
    paths = (files or "").split(",")
    if len(paths) != 1 or not Path(paths[0]).is_file() or hashlib.sha256(Path(paths[0]).read_bytes()).hexdigest() != target["compose_sha256"]:
        raise Refused(f"The running stack does not use {target['tag']}'s {Path(target['compose']).name}.")
    write_json(STATE, target)
    FAILED.unlink(missing_ok=True)
    logger.info("Enrolled %s", target["tag"])
    return 0


def locked():
    """Hold an exclusive lock for the life of the process; the OS releases it if the process dies."""
    DEPLOY.mkdir(parents=True, exist_ok=True)
    handle = open(DEPLOY / "update.lock", "a+")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--enroll", nargs="?", const="latest", metavar="TAG", help="record the running release (default: latest)")
    parser.add_argument("--hosted", action="store_true", help="with --enroll: the hosted stack on a VM (D-032)")
    args = parser.parse_args(argv)
    setup_logging()
    lock = locked()
    if lock is None:
        logger.info("Another update is running")
        return 0
    try:
        if not ok(["docker", "info"]):
            logger.info("Docker is not running; nothing to do")
            return 0
        if args.enroll:
            return enroll(None if args.enroll == "latest" else args.enroll, args.hosted)
        return update()
    except Refused as refused:
        logger.warning("%s", refused)
        return 1
    except (OSError, ValueError) as error:
        # Network, GitHub or registry trouble: nothing was changed, so the next run tries again.
        logger.warning("Could not check for updates (%s); will retry", type(error).__name__)
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
