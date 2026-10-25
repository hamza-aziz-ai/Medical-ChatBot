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
