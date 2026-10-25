import logging
from types import SimpleNamespace

import pytest
from neo4j.exceptions import ServiceUnavailable

from main import create_app

def client(chat_main=lambda text: "answer", seen=None):
    def respond(text, topic=None, selections=(), client=None):
        if seen is not None:
            seen.append({"topic": topic, "selections": selections})
        return {"status": "answer", "reason": "answered", "message": chat_main(text), "answers": [],
                "topic": None, "interpretation": None, "options": []}

    return create_app(chatbot=SimpleNamespace(respond=respond, ready=lambda: (True, None))).test_client()


def test_answer_is_json():
    response = client().get("/", query_string={"search": "what causes asthma"})
    assert response.status_code == 200
    assert response.is_json
    body = response.get_json()
    assert body["search"] == "what causes asthma" and body["message"] == "answer" and body["status"] == "answer"


def test_no_token_is_needed():
    assert client().get("/", query_string={"search": "x"}).status_code == 200


@pytest.mark.parametrize("search", ["", "   ", "x" * 501])
def test_invalid_questions_are_rejected(search):
    response = client().get("/", query_string={"search": search})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_graph_outage_returns_503():
    def fail(text):
        raise ServiceUnavailable("connection refused")

    response = client(fail).get("/", query_string={"search": "x"})
    assert response.status_code == 503
    assert response.is_json


def test_unexpected_error_is_sanitized():
    def fail(text):
        raise ValueError(f"bad input {text}")

    response = client(fail).get("/", query_string={"search": "SECRET_QUESTION"})
    assert response.status_code == 500
    assert "SECRET_QUESTION" not in response.get_data(as_text=True)


def test_http_errors_keep_their_status():
    assert client().get("/missing").status_code == 404


def test_question_never_reaches_the_logs(caplog):
    def fail(text):
        raise ValueError(text)

    sentinel = "PRIVATE_QUESTION_SENTINEL"
    with caplog.at_level(logging.DEBUG):
        client().get("/", query_string={"search": sentinel})
        client(fail).get("/", query_string={"search": sentinel})
    assert sentinel not in caplog.text
    assert logging.getLogger("werkzeug").getEffectiveLevel() >= logging.WARNING


def test_cors_allows_only_configured_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080")
    app_client = client()
    allowed = app_client.options("/", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"})
    blocked = app_client.options("/", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_wildcard_cors_is_refused(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        create_app(chatbot=SimpleNamespace(chat_main=str))


def test_post_is_not_allowed():
    app_client = client()
    for response in (
        app_client.post("/", query_string={"search": "x"}),
        app_client.post("/", json={"search": "x"}),
    ):
        assert response.status_code == 405
        assert response.is_json


def test_405_keeps_the_allow_header():
    response = client().post("/")
    assert response.status_code == 405
    assert response.is_json
    assert {m.strip() for m in response.headers["Allow"].split(",")} >= {"GET"}
    assert "POST" not in response.headers["Allow"]


@pytest.mark.parametrize("origins", ["https://.*", "http://localhost:8080/path", "*", "localhost:8080", "http://local host"])
def test_pattern_and_malformed_origins_are_refused(monkeypatch, origins):
    monkeypatch.setenv("CORS_ORIGINS", origins)
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        create_app(chatbot=SimpleNamespace(chat_main=str))


def test_origins_match_exactly(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:8080")
    app_client = client()

    def allowed(origin):
        response = app_client.options("/", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        return response.headers.get("Access-Control-Allow-Origin") == origin

    assert allowed("http://127.0.0.1:8080")
    for origin in ("http://127.0.0.1:80809", "http://127x0x0x1:8080", "http://127.0.0.1:8080.evil.example", "https://127.0.0.1:8080"):
        assert not allowed(origin)


def test_query_timeout_returns_503():
    from neo4j.exceptions import Neo4jError

    def fail(text):
        # The driver's own factory builds the same ClientError a real timeout raises.
        raise Neo4jError._hydrate_neo4j(code="Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration", message="timed out")

    response = client(fail).get("/", query_string={"search": "x"})
    assert response.status_code == 503
    assert response.is_json


def test_topic_and_selections_are_passed_on_and_bounded():
    seen = []
    app_client = client(seen=seen)
    app_client.get("/", query_string=[("search", "what causes it"), ("topic", "asthma"), ("topic_type", "disease"),
                                      ("selection", "anemia:disease"), ("selection", "no-colon"), ("selection", "x" * 300 + ":disease")]
                   + [("selection", f"n{i}:symptom") for i in range(20)])
    passed = seen[0]
    assert passed["topic"] == {"name": "asthma", "type": "disease"}
    assert passed["selections"][0] == {"name": "anemia", "type": "disease"}
    assert all(len(s["name"]) <= 200 for s in passed["selections"]) and len(passed["selections"]) <= 10
    app_client.get("/", query_string={"search": "x", "topic": "y" * 300, "topic_type": "disease"})
    assert seen[1]["topic"] is None


def test_topic_and_selections_never_reach_the_logs(caplog):
    sentinel = "PRIVATE_TOPIC_SENTINEL"
    with caplog.at_level(logging.DEBUG):
        client().get("/", query_string=[("search", "what causes it"), ("topic", sentinel), ("topic_type", "disease"),
                                         ("selection", f"{sentinel}:symptom")])
    assert sentinel not in caplog.text



# D-022: the readiness route.

def health_client(ready):
    return create_app(chatbot=SimpleNamespace(respond=None, ready=ready)).test_client()


def test_health_says_ok_only_while_ready_and_never_more(caplog):
    caplog.set_level(logging.DEBUG)
    app = health_client(lambda: (True, None))
    caplog.clear()  # the start-up line is not a health log
    response = app.get("/health", query_string={"search": "what causes asthma"})
    assert response.status_code == 200 and response.get_json() == {"status": "ok"}
    assert caplog.text == ""
    response = health_client(lambda: (False, "graph does not match the dictionary")).get("/health")
    assert response.status_code == 503 and response.get_json() == {"status": "unavailable"}
    assert "graph does not match the dictionary" in caplog.text and "asthma" not in caplog.text


def test_health_is_get_only():
    response = health_client(lambda: (True, None)).post("/health")
    assert response.status_code == 405 and "GET" in response.headers["Allow"]


# D-023: questions are refused while the graph is not the one this API's dictionary was published with.

def test_questions_are_refused_while_not_ready_and_nothing_is_answered(caplog):
    answered = []
    app = create_app(chatbot=SimpleNamespace(respond=lambda *args, **kwargs: answered.append(1),
                                             ready=lambda: (False, "graph does not match the dictionary"))).test_client()
    caplog.set_level(logging.DEBUG)
    response = app.get("/", query_string={"search": "what causes asthma"})
    assert response.status_code == 503 and response.get_json() == {"error": "The knowledge graph is unavailable. Please try again later."}
    assert answered == [] and "asthma" not in caplog.text
    # Invalid input is still rejected first, with its own message.
    assert app.get("/", query_string={"search": ""}).status_code == 400
