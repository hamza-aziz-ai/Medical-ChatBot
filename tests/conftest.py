import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakeDriver:
    """Stands in for the neo4j driver: records queries and returns canned rows."""

    def __init__(self, rows=None, results=None):
        self.calls = []
        self.raw_queries = []
        self.rows = rows or []
        self.results = results or {}

    def execute_query(self, query, parameters_=None, **kwargs):
        self.raw_queries.append(query)
        text = getattr(query, "text", query)
        self.calls.append((text, parameters_ or {}))
        rows = self.results.get(text, self.rows)
        return [FakeRecord(row) for row in rows], None, None

    def close(self):
        pass


import pytest


@pytest.fixture(autouse=True)
def ignore_local_env_file(monkeypatch, tmp_path_factory):
    """Keep a developer's real .env out of the tests."""
    import database
    monkeypatch.setattr(database, "ENV_FILE", tmp_path_factory.getbasetemp() / "no-such.env")
