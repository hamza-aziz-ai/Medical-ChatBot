"""Language-model understanding at runtime (D-027), with a fake transport: no model, no network, no graph."""
import json
from unittest import mock

import pytest

import answer_searcher
import chatbot_graph_logic as cg
import understanding as un

ASTHMA, MIGRAINE = {"name": "asthma", "type": "disease"}, {"name": "migraine", "type": "disease"}


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class RecordingSearcher(answer_searcher.AnswerSearcher):
    def __init__(self):
        self.num_limit, self.query_timeout, self.asked = 20, 1, []

    def run(self, sqls):
        results = []
        for group in sqls:
            rows = []
            for _query, params in group["sql"]:
                self.asked.append((group["question_type"], params["name"]))
                rows.append({"subject": params["name"], "value": "synthetic"})
            results.append((group["question_type"], rows))
        return results


class Transport:
    """Replies with fixed text and records what it was sent; replies may name candidates by name for readability."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.sent = reply, error, []

    def __call__(self, messages, url, model):
        self.sent.append(json.loads(messages[1]["content"]))
        if self.error:
            raise self.error
        reply = self.reply
        if isinstance(reply, dict):
            ids = {c["name"] + "/" + c["type"]: c["id"] for c in self.sent[-1]["candidates"]}
            reply = json.dumps({"decision": reply["decision"], "intents": [[i, ids.get(n, n)] for i, n in reply.get("intents", [])]})
        return reply, "gpt-oss:120b"


def bot_with(transport):
    with mock.patch.object(cg, "AnswerSearcher", RecordingSearcher):
        bot = cg.ChatBotGraph()
    bot.understanding = un.Understanding(enabled=True, transport=transport)
    return bot


def test_it_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("LLM_UNDERSTANDING", raising=False)
    assert not un.Understanding().enabled
    monkeypatch.setenv("LLM_UNDERSTANDING", "on")
    assert un.Understanding().enabled
    transport = Transport('{"decision": "answer", "intents": []}')
    assert un.Understanding(enabled=False, transport=transport).route("q", [{"id": "e1"}]) is None and transport.sent == []


def test_a_model_answer_runs_exactly_its_pairs_and_says_a_model_read_it():
    transport = Transport({"decision": "answer", "intents": [["disease_cause", "gout/disease"], ["disease_symptom", "migraine/disease"]]})
    bot = bot_with(transport)
    reply = bot.respond("why does gout happen, and how does migraine show itself", client="a")
    assert reply["status"] == "answer" and reply["reason"] == "answered"
    assert sorted(bot.searcher.asked) == [("disease_cause", "gout"), ("disease_symptom", "migraine")]  # no cross-product
    assert reply["interpretation"]["understood_by"] == "model" and reply["topic"] is None


def test_a_model_refusal_or_clarification_is_final_and_runs_no_query():
    for reply, reason in (({"decision": "unsupported", "intents": []}, "outside_scope"),
                          ({"decision": "unsupported", "intents": [["disease_easy_get", "asthma/disease"]]}, "unsupported_question"),
                          ({"decision": "clarify", "intents": []}, "unclear_subject")):
        bot = bot_with(Transport(reply))
        answer = bot.respond("what causes asthma", client="a")   # the rules alone would answer this
        assert answer["reason"] == reason and bot.searcher.asked == []
        assert answer["interpretation"]["understood_by"] == "model"
    declined = bot_with(Transport({"decision": "unsupported", "intents": []})).respond("what causes asthma", client="a")
    assert declined["topic"] == ASTHMA                           # the one subject named, as the rules do


@pytest.mark.parametrize("transport", [Transport("not json"), Transport(error=un.ModelError("timeout")), Transport(error=OSError("refused"))])
def test_any_unusable_reply_falls_back_to_the_unchanged_rules(transport):
    bot = bot_with(transport)
    reply = bot.respond("what causes asthma", client="a")
    assert reply["status"] == "answer" and bot.searcher.asked == [("disease_cause", "asthma")]
    assert "understood_by" not in reply["interpretation"]


def test_the_topic_is_offered_only_to_a_real_follow_up():
    transport = Transport({"decision": "answer", "intents": [["disease_cause", "asthma/disease"]]})
    bot = bot_with(transport)
    assert bot.respond("what causes it?", topic=ASTHMA, client="a")["status"] == "answer"
    assert transport.sent[-1]["candidates"] == [{"name": "asthma", "type": "disease", "source": "topic", "id": "e1"}]
    for question in ("what are the symptoms of my cousin's condition", "what causes that condition my cousin has"):
        transport.sent.clear()
        reply = bot.respond(question, topic=MIGRAINE, client="a")
        assert transport.sent == [] and reply["reason"] == "no_entity"       # no candidate, no call
    transport.sent.clear()
    bot.respond("and how is gout treated?", topic=MIGRAINE, client="a")
    assert [c["name"] for c in transport.sent[-1]["candidates"]] == ["gout"]  # never the old topic beside a new subject


def test_local_confirmations_and_vetoes_come_first():
    transport = Transport({"decision": "answer", "intents": [["disease_symptom", "anemia/disease"]]})
    bot = bot_with(transport)
    assert bot.respond("what are the symptoms of anemia and which diseases cause anemia", client="a")["reason"] == "ambiguous_type"
    assert bot.respond("how long does asthma last", client="a")["reason"] == "unsupported_question"
    assert bot.respond("what causes asthama", client="a")["reason"] == "possible_typo"
    assert transport.sent == []
    transport.reply = {"decision": "answer", "intents": [["disease_cause", "anemia/disease"]]}
    assert bot.respond("what causes anemia?", client="a")["status"] == "answer"     # two types alone is not ambiguous
    picked = bot.respond("what are the symptoms of anemia and which diseases cause anemia",
                         selections=[{"name": "anemia", "type": "symptom"}], client="a")
    assert {(c["name"], c["type"]) for c in transport.sent[-1]["candidates"]} == {("anemia", "symptom")}
    assert picked["status"] != "answer" or bot.searcher.asked[-1][1] == "anemia"


def test_nothing_from_the_question_or_the_model_reaches_the_logs(caplog):
    caplog.set_level("DEBUG")
    bot = bot_with(Transport({"decision": "answer", "intents": [["disease_cause", "asthma/disease"]]}))
    bot.respond("what causes asthma zzsentinel", client="203.0.113.9")
    bot_with(Transport("Sure: zzmodeltext")).respond("what causes asthma zzsentinel", client="a")
    assert "zzsentinel" not in caplog.text and "zzmodeltext" not in caplog.text and "asthma" not in caplog.text
    assert "203.0.113.9" not in caplog.text and "Language model routed" in caplog.text


def test_attempts_are_budgeted_per_client_and_overall_and_debtors_are_not_forgotten(monkeypatch):
    clock = Clock()
    admission = un.Admission(clock)
    assert [admission.admit("a") for _ in range(3)] == [None, None, "client"]    # a burst of two
    assert admission.admit("b") == "global"                                      # b is new, but the overall burst is spent
    clock.now += 10                                                              # six per minute: one more for a
    assert admission.admit("a") is None and admission.admit("a") == "client"
    clock.now += 60
    monkeypatch.setattr(un, "MAX_CLIENTS", 1)
    full = un.Admission(clock)
    full.admit("a")                                                              # a now owes
    assert full.admit("b") == "table_full" and "a" in full.clients               # no slot: b uses the rules


def test_the_breaker_opens_after_three_failures_and_lets_one_probe_through():
    clock = Clock()
    breaker = un.Breaker(clock)
    for _ in range(3):
        assert breaker.allow()
        breaker.record(False)
    assert not breaker.allow()
    clock.now += un.BREAKER_COOLDOWN_SECONDS
    assert breaker.allow() and not breaker.allow()                               # one probe at a time
    breaker.record(True)
    assert breaker.allow() and breaker.failures == 0


def test_a_valid_refusal_counts_as_a_success_for_the_breaker():
    understanding = un.Understanding(enabled=True, transport=Transport('{"decision": "unsupported", "intents": []}'))
    for _ in range(5):
        understanding.admission = un.Admission()
        understanding.route("q", [{"id": "e1", "name": "asthma", "type": "disease", "source": "mention"}])
    assert understanding.breaker.failures == 0


class Response:
    def __init__(self, chunks, clock, step, status=200):
        self.chunks, self.clock, self.step, self.status = list(chunks), clock, step, status

    def read1(self, size):
        self.clock.now += self.step
        return self.chunks.pop(0) if self.chunks else b""


class Socket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)


def connection_for(response):
    class Connection:
        def __init__(self, host, port, timeout):
            self.sock, self.closed = Socket(), False

        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/api/chat"

        def getresponse(self):
            return response

        def close(self):
            self.closed = True
    return Connection


def test_the_deadline_covers_a_reply_that_arrives_slowly():
    clock = Clock()
    envelope = json.dumps({"message": {"content": "{}"}, "model": "m"}).encode()
    fast = Response([envelope], clock, 0.1)
    assert un.chat([], "http://localhost:11434", "m", clock=clock, connect=connection_for(fast))[0] == "{}"
    dribble = Response([b"x"] * 100, clock, 0.5)                                 # a byte every half second
    with pytest.raises(un.ModelError, match="timeout"):
        un.chat([], "http://localhost:11434", "m", clock=clock, connect=connection_for(dribble))
    huge = Response([b"x" * (un.MAX_REPLY_BYTES + 1)], clock, 0.0)
    with pytest.raises(un.ModelError, match="too large"):
        un.chat([], "http://localhost:11434", "m", clock=clock, connect=connection_for(huge))
    with pytest.raises(un.ModelError, match="HTTP 500"):
        un.chat([], "http://localhost:11434", "m", clock=clock, connect=connection_for(Response([], clock, 0, status=500)))
    with pytest.raises(un.ModelError, match="bad url"):
        un.chat([], "file:///etc/passwd", "m")


def test_compose_turns_it_on_and_every_offline_entry_point_turns_it_off():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert "LLM_UNDERSTANDING: ${LLM_UNDERSTANDING:-on}" in (root / "compose.yaml").read_text(encoding="utf-8")
    assert "export LLM_UNDERSTANDING=off" in (root / "scripts" / "compose_smoke.sh").read_text(encoding="utf-8")
    assert 'os.environ["LLM_UNDERSTANDING"] = "off"' in (root / "scripts" / "evaluate_kg.py").read_text(encoding="utf-8")


class PermitAll:
    def admit(self, client):
        return None


class NeverOpen:
    def allow(self):
        return True

    def cancel(self):
        pass

    def record(self, ok):
        pass


CANDIDATES = [{"id": "e1", "name": "asthma", "type": "disease", "source": "mention"}]


def test_outcomes_are_counted_in_fixed_categories_and_summarised_without_user_data(caplog):
    clock = Clock()
    caplog.set_level("INFO")
    understanding = un.Understanding(enabled=True, clock=clock, admission=PermitAll(), breaker=NeverOpen(),
                                     transport=Transport('{"decision": "answer", "intents": [["disease_cause", "e1"]]}'))
    understanding.route("zzquestion", CANDIDATES, client="203.0.113.9")
    for transport in (Transport("not json"), Transport(error=un.ModelError("timeout")), Transport(error=un.ModelError("HTTP 500")),
                      Transport(error=OSError("refused: zzdetail"))):
        understanding.transport = transport
        understanding.route("zzquestion", CANDIDATES, client="a")
    counts = understanding.counters.snapshot()
    assert {k: counts[k] for k in ("attempts", "routed", "unusable", "failed_timeout", "failed_http", "failed_transport")} == {
        "attempts": 5, "routed": 1, "unusable": 1, "failed_timeout": 1, "failed_http": 1, "failed_transport": 1}
    assert "counts since start" not in caplog.text                              # not due yet
    clock.now += un.SUMMARY_SECONDS
    understanding.route("zzquestion", CANDIDATES, client="a")
    assert caplog.text.count("counts since start") == 1
    assert "zzquestion" not in caplog.text and "203.0.113.9" not in caplog.text and "zzdetail" not in caplog.text


def test_denials_are_counted_where_they_happen():
    understanding = un.Understanding(enabled=True, clock=Clock(), transport=Transport('{"decision": "unsupported", "intents": []}'))
    for client in ("a", "a", "a", "b"):
        understanding.route("q", CANDIDATES, client=client)
    counts = understanding.counters.snapshot()
    assert counts["attempts"] == 2 and counts["denied_client"] == 1 and counts["denied_global"] == 1
    broken = un.Understanding(enabled=True, clock=Clock(), admission=PermitAll(), transport=Transport(error=OSError("down")))
    for _ in range(5):
        broken.route("q", CANDIDATES, client="a")
    assert broken.counters.snapshot()["breaker_skips"] == 2                     # open after three failures


def test_the_harness_alone_can_replace_the_budget_and_breaker():
    understanding = un.Understanding(enabled=True, transport=Transport(error=OSError("down")), admission=PermitAll(), breaker=NeverOpen())
    for _ in range(10):
        understanding.route("q", CANDIDATES, client="a")
    assert understanding.counters.snapshot()["attempts"] == 10                  # no budget, no breaker in the way
    production = un.Understanding(enabled=True)
    assert isinstance(production.admission, un.Admission) and isinstance(production.breaker, un.Breaker)


def test_an_api_key_is_sent_only_over_https_and_never_logged(monkeypatch, caplog):
    # D-033: the hosted stack calls Ollama's cloud directly with a bearer key.
    clock, sent = Clock(), []
    envelope = json.dumps({"message": {"content": "{}"}, "model": "m"}).encode()

    def recording(response):
        base = connection_for(response)

        class Connection(base):
            def request(self, method, path, body, headers):
                sent.append(headers)
        return Connection

    un.chat([], "https://ollama.com", "m", clock=clock, connect=recording(Response([envelope], clock, 0)), api_key="k-secret")
    un.chat([], "http://localhost:11434", "m", clock=clock, connect=recording(Response([envelope], clock, 0)))
    assert sent[0]["Authorization"] == "Bearer k-secret" and "Authorization" not in sent[1]
    with pytest.raises(un.ModelError, match="needs https"):
        un.chat([], "http://example.test", "m", clock=clock, connect=recording(Response([envelope], clock, 0)), api_key="k-secret")
    assert len(sent) == 2

    monkeypatch.setenv("OLLAMA_API_KEY", "k-secret")
    understanding = un.Understanding(enabled=True, url="http://example.test")
    with caplog.at_level("DEBUG"):
        assert understanding.route("q", [{"id": "e1", "name": "asthma", "type": "disease", "source": "rules"}]) is None
    assert "k-secret" not in caplog.text


def test_the_overall_budget_can_be_lowered_for_the_public_site(monkeypatch):
    monkeypatch.setenv("LLM_GLOBAL_PER_MINUTE", "6")
    clock = Clock()
    admission = un.Admission(clock)
    assert admission.global_per_minute == 6
    admitted = [admission.admit(f"client-{i}") for i in range(2)]
    assert admitted == [None, None] and admission.admit("client-9") == "global"
    clock.now += 10  # 6 per minute refills one attempt every 10 s
    assert admission.admit("client-9") is None
    monkeypatch.setenv("LLM_GLOBAL_PER_MINUTE", "0")
    with pytest.raises(ValueError):
        un.Admission(clock)
