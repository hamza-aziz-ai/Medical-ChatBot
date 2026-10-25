"""The per-client spelling-suggestion budget (A-14, D-025)."""
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import chatbot_graph_logic as cg
import main
from answer_searcher import AnswerSearcher
from conftest import FakeDriver
from question_classifier import QuestionClassifier
from question_parser import QuestionParser

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def spend(seconds, clock, result="done"):
    def work(deadline):
        clock.now += seconds
        return result
    return work


def test_a_grant_is_the_remaining_credit_at_most_150_ms():
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock)
    seen = []
    budget.run("a", lambda deadline: seen.append(deadline - clock.now))
    assert seen == [pytest.approx(0.15)]
    budget.run("b", spend(0.95, clock))  # b now has about 0.05 s left
    budget.run("b", lambda deadline: seen.append(deadline - clock.now))
    assert seen[1] == pytest.approx(0.05, abs=1e-3)


def test_preparation_counts_against_the_deadline():
    clock = Clock()
    classifier = QuestionClassifier()

    def work(deadline):
        clock.now += 0.2  # slow preparation of the windows
        return classifier.close_matches(["asthama"], clock=clock, deadline=deadline)

    assert cg.SuggestionBudget(clock=clock).run("a", work) == []  # no window starts after the deadline


def test_overruns_become_debt_and_refill_restores_suggestions():
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock)
    assert budget.run("a", spend(0.6, clock)) == "done"
    assert budget.run("a", spend(0.6, clock)) == "done"          # overruns the last ~0.4 s: about 0.2 s of debt
    assert budget.clients["a"][0] < -0.15
    assert budget.run("a", spend(0.1, clock)) is None            # no credit: no work at all
    clock.now += 6                                               # 0.1 s refilled: still in debt
    assert budget.run("a", spend(0.0, clock)) is None
    clock.now += 12                                              # debt repaid and some credit back
    assert budget.run("a", spend(0.0, clock)) == "done"
    clock.now += 3600
    budget.run("a", lambda deadline: None)
    assert budget.clients["a"][0] <= cg.SUGGESTION_CAPACITY_SECONDS  # refill never exceeds the capacity


def test_failed_work_is_still_charged():
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock)

    def failing(deadline):
        clock.now += 0.5
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        budget.run("a", failing)
    assert budget.clients["a"][0] == pytest.approx(0.5, abs=0.01)


def test_clients_are_isolated():
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock)
    budget.run("a", spend(1.5, clock))
    assert budget.run("a", spend(0.0, clock)) is None
    assert budget.run("b", spend(0.0, clock)) == "done"


def test_a_full_table_forgets_only_idle_clients_never_debtors():
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock, max_clients=2)
    budget.run("a", spend(0.0, clock))
    budget.run("b", spend(0.0, clock))
    assert budget.run("c", spend(0.0, clock)) == "done"     # a and b were idle and full: forgotten
    budget.run("c", spend(2.0, clock))
    budget.run("d", spend(2.0, clock))                      # c and d both owe
    assert budget.run("e", spend(0.0, clock)) is None       # no safe slot: e gets no suggestions
    assert set(budget.clients) == {"c", "d"} and budget.clients["c"][0] < 0


def test_concurrent_requests_never_spend_the_same_credit():
    budget = cg.SuggestionBudget(clock=time.monotonic, capacity=0.12)
    admitted = []

    def work(deadline):
        admitted.append(1)
        time.sleep(0.05)

    threads = [threading.Thread(target=budget.run, args=("a", work)) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 0.12 s of credit at 0.05 s each: at most three calls start (the last one overrunning), never all six.
    assert 1 <= len(admitted) <= 3


def test_denial_is_logged_once_per_transition_without_an_address(caplog):
    clock = Clock()
    budget = cg.SuggestionBudget(clock=clock)
    budget.run("203.0.113.9", spend(2.0, clock))
    caplog.set_level("INFO")
    for _ in range(3):
        budget.run("203.0.113.9", spend(0.0, clock))
    assert caplog.text.count("over its budget") == 1 and "203.0.113.9" not in caplog.text


def test_an_exhausted_client_still_gets_answers_but_no_spelling_suggestions():
    bot = cg.ChatBotGraph.__new__(cg.ChatBotGraph)
    bot.classifier, bot.parser, bot.availability = QuestionClassifier(), QuestionParser(), {}
    bot.searcher = AnswerSearcher(driver=FakeDriver(rows=[{"subject": "asthma", "value": "dust"}]))
    clock = Clock()
    bot.suggestion_budget = cg.SuggestionBudget(clock=clock)
    assert bot.respond("what causes asthama?", client="a")["reason"] == "possible_typo"
    bot.suggestion_budget.clients["a"][0] = -1.0
    reply = bot.respond("what causes asthama?", client="a")
    assert reply["reason"] == "no_entity" and reply["options"] == []
    assert bot.respond("what causes asthma?", client="a")["status"] == "answer"


def test_the_client_address_comes_from_nginx_only_where_the_image_says_so(monkeypatch):
    def request(header=None, peer="172.18.0.4"):
        return SimpleNamespace(headers={"X-Real-IP": header} if header is not None else {}, remote_addr=peer)

    monkeypatch.delenv("TRUST_PROXY_HEADER", raising=False)
    assert main.client_address(request("198.51.100.7", peer="127.0.0.1")) == "127.0.0.1"   # development: header ignored
    monkeypatch.setenv("TRUST_PROXY_HEADER", "1")
    assert main.client_address(request("198.51.100.7")) == "198.51.100.7"
    assert main.client_address(request("2001:DB8:0:0::1")) == "2001:db8::1"                 # canonical form
    assert main.client_address(request("not an address")) == "172.18.0.4"                  # malformed: socket peer
    assert main.client_address(request(None, peer=None)) == "unknown"


def test_nginx_overwrites_the_header_and_the_api_image_trusts_it():
    assert "proxy_set_header X-Real-IP $remote_addr;" in (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")
    assert "ENV TRUST_PROXY_HEADER=1" in (ROOT / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
