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

    expected = (
        "I cannot answer this question from the available medical "
        "knowledge graph. Please consult a qualified medical professional."
    )
    rows = [
        {"subject": "asthma", "value": "fixture value"},
        {"subject": "asthma", "value": ["fixture treatment"]},
    ]
    unsupported = ("disease_last_time", "disease_cure_probability", "disease_easy_get")

    def ask(intents, result_rows):
        result = {} if intents is None else {
            "arguments": {"asthma": ["disease"], "wheeze": ["symptom"]},
            "question_types": intents,
        }
        bot.classifier = SimpleNamespace(classify=lambda _: result)
        driver.calls.clear()
        driver.rows = result_rows
        with patch.object(builtins, "open", side_effect=AssertionError("unexpected runtime asset read")):
            return bot.chat_main("fixture")

    assert ask(None, []) == expected
    assert ask([], []) == expected
    assert ask(["disease_cause"], []) == expected

    for intent in unsupported:
        assert bot.parser.sql_transfer(intent, ["asthma"]) == []
        assert not bot.searcher.answer_prettify(intent, rows)
        for intents in ([intent], ["disease_cause", intent]):
            assert ask(intents, rows) == expected
            assert driver.calls == []

    for intent in (
        "disease_symptom", "symptom_disease", "disease_cause",
        "disease_prevention", "disease_cure_way",
        "disease_description", "disease_accompany",
    ):
        answer = ask([intent], rows)
        assert answer and answer != expected
        assert driver.calls
