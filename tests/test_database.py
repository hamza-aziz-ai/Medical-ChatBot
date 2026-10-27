import pytest

import database


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "soon"])
def test_invalid_query_timeouts_are_refused(monkeypatch, value):
    monkeypatch.setenv("NEO4J_QUERY_TIMEOUT", value)
    with pytest.raises(RuntimeError, match="NEO4J_QUERY_TIMEOUT"):
        database.query_timeout()


def test_default_query_timeout(monkeypatch):
    monkeypatch.delenv("NEO4J_QUERY_TIMEOUT", raising=False)
    assert database.query_timeout() == 5.0


@pytest.mark.parametrize("uri", ["http://localhost:7474", "https://db.example:7473", "localhost:7687"])
def test_non_bolt_uris_are_refused(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    with pytest.raises(RuntimeError, match="Bolt scheme"):
        database.database_uri()


@pytest.mark.parametrize("uri", ["neo4j://localhost:7687", "bolt://127.0.0.1:7687", "neo4j+s://db.example:7687"])
def test_bolt_uris_are_accepted(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    assert database.database_uri() == uri


def test_env_file_fills_missing_variables_only(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nNEO4J_PASSWORD='from file'\nNEO4J_USER=fileuser\nNEO4J_URI=\nEXAMPLE_SETTING=\"tok\"\nnot a line\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("EXAMPLE_SETTING", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("NEO4J_USER", "shell")
    database.load_env_file(env)
    import os
    assert os.environ["NEO4J_PASSWORD"] == "from file"
    assert os.environ["EXAMPLE_SETTING"] == "tok"
    assert os.environ["NEO4J_USER"] == "shell"
    assert "NEO4J_URI" not in os.environ
    for key in ("NEO4J_PASSWORD", "EXAMPLE_SETTING"):
        monkeypatch.delenv(key)


def test_missing_env_file_is_ignored(tmp_path):
    database.load_env_file(tmp_path / "absent.env")


def test_the_api_fails_fast_while_the_importer_stays_patient(monkeypatch):
    # D-032: an unreachable graph must answer 503 well inside Gunicorn's 30 s watchdog; the importer keeps waiting longer.
    seen = []
    monkeypatch.setattr(database.GraphDatabase, "driver", lambda uri, **kwargs: seen.append(kwargs) or object())
    monkeypatch.setenv("NEO4J_PASSWORD", "x")
    from answer_searcher import AnswerSearcher

    AnswerSearcher()
    database.create_driver()
    api, importer = seen
    assert {k: api[k] for k in database.API_DRIVER_SETTINGS} == database.API_DRIVER_SETTINGS
    assert importer["connection_timeout"] == 10 and importer["max_transaction_retry_time"] == 15
    assert "connection_acquisition_timeout" not in importer
