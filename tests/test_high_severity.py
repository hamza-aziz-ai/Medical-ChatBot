import builtins
from types import SimpleNamespace
from unittest.mock import patch

import chatbot_graph_logic as cg
from answer_searcher import AnswerSearcher
from conftest import FakeDriver
from question_parser import QuestionParser


def test_high_severity_paths():
    driver = FakeDriver()
    bot = cg.ChatBotGraph.__new__(cg.ChatBotGraph)
    bot.parser = QuestionParser()
    bot.searcher = AnswerSearcher(driver=driver)

    rows = [
        {"subject": "asthma", "value": "fixture value"},
        {"subject": "asthma", "value": ["fixture treatment"]},
    ]
    unsupported = ("disease_last_time", "disease_cure_probability", "disease_easy_get")

    bot.availability = {"asthma": ["disease_symptom", "disease_cause"]}

    def ask(intents, result_rows, arguments=None):
        arguments = arguments or {"asthma": ["disease"], "wheeze": ["symptom"]}
        bot.classifier = SimpleNamespace(
            check_medical=lambda _, hits=None: {} if intents is None else dict(arguments),
            close_matches=lambda phrases, accept=None: [],
            intent_keywords=lambda: [],
            classify_with=lambda _, args: {"arguments": args, "question_types": intents},
            has_intent_keyword=lambda _: True,
        )
        driver.calls.clear()
        driver.rows = result_rows
        with patch.object(builtins, "open", side_effect=AssertionError("unexpected runtime asset read")):
            return bot.respond("fixture")

    def abstained(reply, reason):
        return reply["status"] == "abstain" and reply["reason"] == reason and reply["message"].endswith(cg.CONSULT)

    assert abstained(ask(None, []), "no_entity")
    assert abstained(ask([], []), "no_facts")
    assert abstained(ask(["disease_cause"], []), "no_facts")

    for intent in unsupported:
        assert bot.parser.sql_transfer(intent, ["asthma"]) == []
        assert not bot.searcher.answer_prettify(intent, rows)
        for intents in ([intent], ["disease_cause", intent]):
            assert abstained(ask(intents, rows), "unsupported_question")
            assert driver.calls == []
            # One subject gives a topic; the abstention still makes no database call.
            assert abstained(ask(intents, rows, {"asthma": ["disease"]}), "unsupported_question")
            assert driver.calls == []

    for intent in (
        "disease_symptom", "symptom_disease", "disease_cause",
        "disease_prevention", "disease_cure_way",
        "disease_description", "disease_accompany",
    ):
        reply = ask([intent], rows)
        assert reply["status"] == "answer" and reply["message"]
        assert driver.calls
