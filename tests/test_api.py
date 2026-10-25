import logging
from types import SimpleNamespace

import pytest
from neo4j.exceptions import ServiceUnavailable

from main import create_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def client(chat_main=lambda text: "answer"):
    return create_app(chatbot=SimpleNamespace(chat_main=chat_main), api_token=TOKEN).test_client()


def test_answer_is_json():
    response = client().get("/", query_string={"search": "what causes asthma"}, headers=AUTH)
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"search": "what causes asthma", "message": "answer"}


def test_missing_or_wrong_token_is_rejected():
    assert client().get("/", query_string={"search": "x"}).status_code == 401
    assert client().get("/", query_string={"search": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401


@pytest.mark.parametrize("search", ["", "   ", "x" * 501])
def test_invalid_questions_are_rejected(search):
    response = client().get("/", query_string={"search": search}, headers=AUTH)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_graph_outage_returns_503():
    def fail(text):
        raise ServiceUnavailable("connection refused")

    response = client(fail).get("/", query_string={"search": "x"}, headers=AUTH)
    assert response.status_code == 503
    assert response.is_json


def test_unexpected_error_is_sanitized():
    def fail(text):
        raise ValueError(f"bad input {text}")

    response = client(fail).get("/", query_string={"search": "SECRET_QUESTION"}, headers=AUTH)
    assert response.status_code == 500
    assert "SECRET_QUESTION" not in response.get_data(as_text=True)


def test_http_errors_keep_their_status():
    assert client().get("/missing", headers=AUTH).status_code == 404


def test_question_never_reaches_the_logs(caplog):
    def fail(text):
        raise ValueError(text)

    sentinel = "PRIVATE_QUESTION_SENTINEL"
    with caplog.at_level(logging.DEBUG):
        client().get("/", query_string={"search": sentinel}, headers=AUTH)
        client(fail).get("/", query_string={"search": sentinel}, headers=AUTH)
    assert sentinel not in caplog.text
    assert logging.getLogger("werkzeug").getEffectiveLevel() >= logging.WARNING


def test_cors_allows_only_configured_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080")
    app_client = client()
    allowed = app_client.options("/", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"})
    blocked = app_client.options("/", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_wildcard_cors_and_missing_token_are_refused(monkeypatch):
    monkeypatch.delenv("CHATBOT_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        create_app(chatbot=SimpleNamespace(chat_main=str))
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        create_app(chatbot=SimpleNamespace(chat_main=str), api_token=TOKEN)


def test_post_is_not_allowed():
    app_client = client()
    for response in (
        app_client.post("/", query_string={"search": "x"}, headers=AUTH),
        app_client.post("/", json={"search": "x"}, headers=AUTH),
    ):
        assert response.status_code == 405
        assert response.is_json
