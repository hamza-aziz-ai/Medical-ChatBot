"""The rollback drill's own guards (offline). The live drill is run by hand: python scripts/rollback_drill.py."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("rollback_drill", SCRIPTS / "rollback_drill.py")
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


def test_the_drill_environment_carries_nothing_compose_or_the_stack_would_read():
    env = drill.drill_env({"PATH": "p", "SystemRoot": "s", "DOCKER_HOST": "d", "NEO4J_PASSWORD": "secret",
                           "WEB_PORT": "8080", "API_IMAGE": "x", "COMPOSE_PROJECT_NAME": "medical-chatbot",
                           "COMPOSE_FILE": "compose.yaml", "LOG_DIR": "logs"})
    assert env == {"PATH": "p", "SystemRoot": "s", "DOCKER_HOST": "d"}


def test_existing_resources_with_the_drill_name_stop_the_drill():
    def runner(output):
        return lambda args: subprocess.CompletedProcess(args, 0, output, "")

    drill.ensure_unused("medical-chatbot-drill-ab12", runner(""))
    with pytest.raises(drill.DrillError, match="already exist"):
        drill.ensure_unused("medical-chatbot-drill-ab12", runner("c0ffee\n"))
    with pytest.raises(drill.DrillError):
        drill.ensure_unused("medical-chatbot-drill-ab12", lambda args: subprocess.CompletedProcess(args, 1, "", ""))


def test_the_drill_targets_its_own_project_and_folder_and_leaves_the_updater_defaults_alone(tmp_path):
    us = drill.load_updater(tmp_path, "medical-chatbot-drill-ab12")
    assert us.ROOT == tmp_path and us.PROJECT == "medical-chatbot-drill-ab12"
    assert us.VOLUME == "medical-chatbot-drill-ab12_neo4j-data"
    assert all(Path(p).is_relative_to(tmp_path) for p in (us.DEPLOY, us.STATE, us.JOURNAL, us.FAILED))
    spec = importlib.util.spec_from_file_location("update_stack_defaults", SCRIPTS / "update_stack.py")
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    assert real.PROJECT == "medical-chatbot" and real.VOLUME == "medical-chatbot_neo4j-data"
    assert real.DEPLOY == SCRIPTS.parent / "deploy"


def test_an_injected_change_that_did_not_commit_fails_the_drill(monkeypatch):
    monkeypatch.setattr(drill, "cypher", lambda project, password, query: [])
    with pytest.raises(drill.DrillError, match="not committed"):
        drill.mutate("p", "pw", "n")
    monkeypatch.setattr(drill, "cypher", lambda project, password, query: ['"replacement"'] if "RETURN" in query else [])
    drill.mutate("p", "pw", "n")
