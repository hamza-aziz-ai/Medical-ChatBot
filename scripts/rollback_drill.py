"""Rollback drill for scripts/update_stack.py on a throwaway stack (D-021). Run by hand; needs Docker and GitHub.

    python scripts/rollback_drill.py

Starts its own Compose project (medical-chatbot-drill-<nonce>) from the real v1.1.4 release, enrols it, and updates it
to the real v1.1.5 release twice with a fault injected after a committed change to the graph:
  1. the importer step fails: the same run must restore the backup and v1.1.4;
  2. the updater process dies (os._exit) mid-update: a fresh process must recover from the journal.
Each time the drill checks that the graph change was undone, the old images run, /api/health is ok and a question
is answered. Only release discovery is replaced; every Docker step is real. The owner's stack, .env and deploy/
are never touched, and the drill project is torn down at the end.
"""
import importlib.util
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT, TARGET = "v1.1.4", "v1.1.5"
CRASH_EXIT = 97
# Variables Compose or the stack would read; the drill builds its environment from a short allow-list instead.
KEEP_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "DOCKER_HOST", "DOCKER_CONTEXT",
            "DOCKER_CONFIG")


class DrillError(Exception):
    pass


def drill_env(environ):
    """Only OS essentials and Docker's own connection settings: nothing that could override the scratch .env."""
    return {key: value for key, value in environ.items() if key.upper() in KEEP_ENV}


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def load_updater(scratch, project):
    """A private copy of the updater pointed at the scratch folder and the drill project; its defaults are untouched."""
    spec = importlib.util.spec_from_file_location(f"update_stack_drill_{project}", ROOT / "scripts" / "update_stack.py")
    us = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(us)
    us.ROOT, us.PROJECT, us.VOLUME = scratch, project, f"{project}_neo4j-data"
    us.DEPLOY = scratch / "deploy"
    us.STATE, us.JOURNAL, us.FAILED = us.DEPLOY / "current.json", us.DEPLOY / "journal.json", us.DEPLOY / "failed.json"
    return us


def ensure_unused(project, runner=run):
    """Refuse to run if anything already carries the drill project's name: teardown would delete it."""
    checks = [["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
              ["docker", "volume", "ls", "-q", "--filter", f"name={project}"],
              ["docker", "network", "ls", "-q", "--filter", f"name={project}"]]
    for args in checks:
        result = runner(args)
        if result.returncode != 0 or result.stdout.strip():
            raise DrillError(f"Resources named {project} already exist, or Docker is unavailable; not starting")


def neo4j_container(project):
    found = run(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
                 "--filter", "label=com.docker.compose.service=neo4j"]).stdout.split()
    if len(found) != 1:
        raise DrillError("Could not find the drill's Neo4j container")
    return found[0]


def cypher(project, password, query):
    """Run a query in the drill's own Neo4j container; never through the repository's Compose configuration."""
    result = run(["docker", "exec", "-e", "NEO4J_USERNAME=neo4j", "-e", f"NEO4J_PASSWORD={password}", neo4j_container(project),
                  "cypher-shell", "--format", "plain", query])
    if result.returncode != 0:
        raise DrillError(f"Query failed in the drill database (exit {result.returncode})")
    return result.stdout.strip().splitlines()[1:]


def graph_counts(project, password):
    owned = cypher(project, password, "MATCH (n {owner: 'medical-chatbot-importer'}) RETURN count(n)")[0]
    edges = cypher(project, password, "MATCH ()-[r {owner: 'medical-chatbot-importer'}]->() RETURN count(r)")[0]
    return int(owned), int(edges)


def markers(project, password, nonce):
    rows = cypher(project, password, f"MATCH (m:DrillMarker {{nonce: '{nonce}'}}) RETURN m.kind ORDER BY m.kind")
    return [row.strip('"') for row in rows]


def mutate(project, password, nonce):
    """The injected change: replace the original marker, then prove the commit happened."""
    cypher(project, password, f"MATCH (m:DrillMarker {{nonce: '{nonce}', kind: 'original'}}) DELETE m "
                              f"CREATE (:DrillMarker {{nonce: '{nonce}', kind: 'replacement'}})")
    if markers(project, password, nonce) != ["replacement"]:
        raise DrillError("The injected change was not committed; the drill would prove nothing")


def child(scratch, project, mode):
    """Run one updater pass in this process with the fault injected at the importer step (mode: fail, crash, none)."""
    os.environ.clear()
    os.environ.update(json.loads((scratch / "env.json").read_text(encoding="utf-8")))
    settings = json.loads((scratch / "drill.json").read_text(encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="  updater: %(message)s")
    us = load_updater(scratch, project)
    lock = us.locked()  # a process that died holding it must have released it
    if lock is None:
        print("The updater lock is still held", file=sys.stderr)
        return 3
    target = us.fetch_release(TARGET)
    us.fetch_release = lambda tag=None: target  # the only substitution: discovery always offers the real v1.1.5
    real_compose = us.compose

    def compose(deployment, *args):
        if "importer" in args and mode != "none":
            mutate(project, settings["password"], settings["nonce"])
            (scratch / "mutated.flag").write_text(mode, encoding="utf-8")
            if mode == "crash":
                os._exit(CRASH_EXIT)  # die mid-maintenance: no recovery, no cleanup, the journal stays
            return False
        return real_compose(deployment, *args)

    us.compose = compose
    return us.update()


def spawn(scratch, project, mode):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(scratch), project, mode],
                            env=json.loads((scratch / "env.json").read_text(encoding="utf-8")))
    return result.returncode


def check_restored(us, current, project, settings, before):
    state = json.loads(us.STATE.read_text(encoding="utf-8"))
    checks = {
        "previous release recorded": state["tag"] == CURRENT,
        "target marked failed": json.loads(us.FAILED.read_text(encoding="utf-8")).get("tag") == TARGET,
        "journal cleared": not us.JOURNAL.exists(),
        "previous images running": us.running_matches(current),
        "health, readiness and a question": us.healthy(current),
        "graph change undone": markers(project, settings["password"], settings["nonce"]) == ["original"],
        "graph counts unchanged": graph_counts(project, settings["password"]) == before,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise DrillError("Not restored: " + ", ".join(failed))
    return list(checks)


def main():
    nonce = secrets.token_hex(4)
    project = f"medical-chatbot-drill-{nonce}"
    scratch = Path(tempfile.mkdtemp(prefix="rollback-drill-"))
    env = drill_env(os.environ)
    os.environ.clear()
    os.environ.update(env)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = {"password": secrets.token_urlsafe(18), "nonce": nonce}
    (scratch / ".env").write_text(f"NEO4J_PASSWORD={settings['password']}\nWEB_PORT={port}\nLOG_LEVEL=INFO\n", encoding="utf-8")
    (scratch / "env.json").write_text(json.dumps(env), encoding="utf-8")
    (scratch / "drill.json").write_text(json.dumps(settings), encoding="utf-8")
    us = load_updater(scratch, project)
    current = None
    timings, outcome = {}, 1
    try:
        ensure_unused(project)
        old, new = us.download(us.fetch_release(CURRENT)), us.download(us.fetch_release(TARGET))
        if not (old["compose_sha256"] == new["compose_sha256"] and old["health"] and new["health"]
                and old["api_image"] != new["api_image"]):
            raise DrillError(f"{CURRENT} and {TARGET} are not a suitable pair (compose, health capability, images)")
        current = old
        start = time.monotonic()
        steps = [("pull",), ("up", "-d", "--wait", "neo4j"), ("--profile", "init", "run", "--rm", "importer"),
                 ("up", "-d", "--no-build", "--pull", "never", "api", "web")]
        for step in steps:
            if not us.compose(current, *step):
                raise DrillError(f"Could not start the drill stack ({step[0]})")
        if not us.healthy(current):
            raise DrillError("The drill stack did not become healthy")
        if us.enroll(CURRENT) != 0:
            raise DrillError("Enrolment failed")
        timings["start and enrol"] = time.monotonic() - start
        cypher(project, settings["password"], f"CREATE (:DrillMarker {{nonce: '{nonce}', kind: 'original'}})")
        before = graph_counts(project, settings["password"])

        for scenario, mode in (("failure after the change", "fail"), ("process death after the change", "crash")):
            us.FAILED.unlink(missing_ok=True)
            (scratch / "mutated.flag").unlink(missing_ok=True)
            start = time.monotonic()
            code = spawn(scratch, project, mode)
            if not (scratch / "mutated.flag").exists():
                raise DrillError(f"{scenario}: the injected change never ran (exit {code})")
            if mode == "crash":
                if code != CRASH_EXIT or not us.JOURNAL.exists():
                    raise DrillError(f"{scenario}: the updater did not die mid-update as planned (exit {code})")
                code = spawn(scratch, project, "none")  # a fresh process recovers from the journal
            if code != 1:
                raise DrillError(f"{scenario}: expected the update to report failure, got exit {code}")
            proved = check_restored(us, current, project, settings, before)
            if spawn(scratch, project, "none") != 0 or json.loads(us.STATE.read_text(encoding="utf-8"))["tag"] != CURRENT:
                raise DrillError(f"{scenario}: a later run retried the failed release")
            timings[scenario] = time.monotonic() - start
            print(f"PASS {scenario}: " + "; ".join(proved) + f" ({timings[scenario]:.0f} s)")
        outcome = 0
    except DrillError as error:
        print(f"FAIL {error}", file=sys.stderr)
    finally:
        cleanup = [sys.executable, "-c", "print('nothing to clean up')"]
        if current is not None:
            if us.compose(current, "down", "-v", "--remove-orphans"):
                shutil.rmtree(scratch, ignore_errors=True)
                print(f"Removed the drill project {project} and its scratch folder")
            else:
                outcome = 1
                print(f"Teardown failed; scratch kept at {scratch}. Remove it with: docker compose -p {project} "
                      f"-f {current['compose']} --project-directory {scratch} --env-file {scratch / '.env'} down -v",
                      file=sys.stderr)
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    print(json.dumps({"releases": [CURRENT, TARGET], "outcome": "pass" if outcome == 0 else "fail",
                      "seconds": {k: round(v) for k, v in timings.items()}, "platform": sys.platform}))
    return outcome


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        sys.exit(child(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
    sys.exit(main())
