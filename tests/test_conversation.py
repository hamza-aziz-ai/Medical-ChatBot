"""Guided conversation (D-015): follow-ups, clarification, explained abstentions and suggestion chips."""
import json
from types import SimpleNamespace

import pytest

import chatbot_graph_logic as cg
from answer_searcher import AnswerSearcher
from conftest import FakeDriver
from question_classifier import QuestionClassifier
from question_parser import QuestionParser

ALL_DISEASE_INTENTS = ["disease_symptom", "disease_cause", "disease_prevention", "disease_cure_way",
                       "disease_accompany", "disease_description"]
CLASSIFIER = QuestionClassifier()


def make_bot(rows=None, availability=None):
    driver = FakeDriver(rows=rows if rows is not None else [{"subject": "asthma", "value": "dust"}])
    bot = cg.ChatBotGraph.__new__(cg.ChatBotGraph)
    bot.classifier = CLASSIFIER
    bot.parser = QuestionParser()
    bot.searcher = AnswerSearcher(driver=driver)
    bot.availability = availability if availability is not None else {"asthma": ALL_DISEASE_INTENTS}
    return bot, driver


ASTHMA = {"name": "asthma", "type": "disease"}


def intents_of(reply):
    return [item["intent"] for item in reply["interpretation"]["intents"]]


@pytest.mark.parametrize("question, intent", [
    ("what causes it?", "disease_cause"),
    ("And prevention?", "disease_prevention"),
    ("how is it treated?", "disease_cure_way"),
])
def test_follow_ups_reuse_the_confirmed_topic(question, intent):
    bot, driver = make_bot()
    reply = bot.respond(question, topic=ASTHMA)
    assert reply["status"] == "answer"
    assert reply["interpretation"]["used_topic"] is True
    assert reply["interpretation"]["entities"] == [{"name": "asthma", "types": ["disease"]}]
    assert intents_of(reply) == [intent]
    assert reply["topic"] == ASTHMA


@pytest.mark.parametrize("question", [
    "what causes this 糖尿病?",
    "and prevention of 12345?",
    "what about flu?",
    "what causes zzyzx?",
    "what causes it in children?",
])
def test_a_question_naming_anything_else_never_inherits_the_topic(question):
    bot, driver = make_bot()
    reply = bot.respond(question, topic=ASTHMA)
    assert reply["status"] == "abstain" and reply["reason"] == "no_entity"
    assert driver.calls == []


@pytest.mark.parametrize("topic", [
    {"name": "not a disease", "type": "disease"},
    {"name": "asthma", "type": "department"},
    {"name": "neurology", "type": "disease"},
    "asthma",
    None,
])
def test_invalid_topics_are_ignored(topic):
    bot, driver = make_bot()
    assert bot.respond("what causes it?", topic=topic)["reason"] == "no_entity"
    assert driver.calls == []


def test_an_explicit_new_subject_wins_over_the_topic():
    bot, _ = make_bot()
    reply = bot.respond("what causes migraine?", topic=ASTHMA)
    assert reply["interpretation"]["used_topic"] is False
    assert reply["interpretation"]["entities"][0]["name"] == "migraine"


def test_unsupported_questions_abstain_without_touching_the_database():
    bot, driver = make_bot()
    reply = bot.respond("how long does asthma last?")
    assert reply["status"] == "abstain" and reply["reason"] == "unsupported_question"
    assert reply["options"] == [] and driver.calls == []
    assert intents_of(reply) == ["disease_last_time"]


def test_department_only_questions_are_explained():
    bot, driver = make_bot()
    reply = bot.respond("tell me about neurology")
    assert reply["status"] == "abstain" and reply["reason"] == "unsupported_entity"
    assert driver.calls == []


def test_ambiguous_names_are_clarified_and_the_choice_keeps_the_original_question():
    bot, _ = make_bot(rows=[{"subject": "anemia", "value": "tiredness"}])
    question = "what are the symptoms of anemia"
    reply = bot.respond(question)
    assert reply["status"] == "clarify" and reply["reason"] == "ambiguous_type"
    assert {option["question"] for option in reply["options"]} == {question}
    as_disease = next(option for option in reply["options"] if option["selections"][-1]["type"] == "disease")
    answered = bot.respond(question, selections=as_disease["selections"])
    assert answered["status"] == "answer"
    assert answered["interpretation"]["entities"] == [{"name": "anemia", "types": ["disease"]}]
    assert intents_of(answered) == ["disease_symptom"]


def test_successive_clarifications_accumulate_every_choice():
    bot, _ = make_bot(rows=[{"subject": "anemia", "value": "tiredness"}])
    question = "symptoms of acute gastric dilatation and anemia"
    selections, reply = [], bot.respond(question)
    for _ in range(3):
        if reply["status"] != "clarify":
            break
        selections = next(o for o in reply["options"] if o["selections"][-1]["type"] == "disease")["selections"]
        reply = bot.respond(question, selections=selections)
    assert reply["status"] == "answer"
    assert {e["name"]: e["types"] for e in reply["interpretation"]["entities"]} == {
        "acute gastric dilatation": ["disease"], "anemia": ["disease"]}


def test_selections_about_other_names_or_types_are_ignored():
    bot, _ = make_bot()
    reply = bot.respond("what are the symptoms of anemia", selections=[
        {"name": "asthma", "type": "disease"}, {"name": "anemia", "type": "department"}, "junk"])
    assert reply["status"] == "clarify"


def test_unsupported_intents_are_vetoed_before_any_clarification():
    bot, driver = make_bot()
    reply = bot.respond("how long do the symptoms of anemia last")
    assert reply["status"] == "abstain" and reply["reason"] == "unsupported_question"
    assert driver.calls == []


def test_suggestions_offer_only_answerable_new_intents_for_the_topic():
    bot, _ = make_bot(availability={"asthma": ["disease_symptom", "disease_cause", "disease_prevention"]})
    reply = bot.respond("what causes asthma?")
    offered = [option["question"] for option in reply["options"]]
    assert offered == ["What are the symptoms of asthma?", "How can I prevent asthma?"]
    assert all(option["topic"] == ASTHMA for option in reply["options"])


def test_every_suggestion_in_the_dictionary_round_trips_to_its_intent():
    bot, _ = make_bot(availability={name: ALL_DISEASE_INTENTS for name in CLASSIFIER.disease_words})
    for name in CLASSIFIER.disease_words:
        for option in bot.suggestions({"name": name, "type": "disease"}):
            intent = next(i for i, text in cg.QUESTION_FOR.items() if text.format(name) == option["question"])
            assert CLASSIFIER.classify_with(option["question"], {name: ["disease"]})["question_types"] == [intent]
    # BUG-002: "infection" inside these names is no longer read as an intent, so their chips are offered again.
    for name in ["deep palm infection", "non-cholesteric infection", "retroperitoneal infection and abscess"]:
        assert len(bot.suggestions({"name": name, "type": "disease"})) == cg.MAX_SUGGESTIONS


def test_a_listed_intent_with_no_rows_still_gets_a_clean_answer():
    bot, _ = make_bot(rows=[])
    reply = bot.respond("what causes asthma?")
    assert reply["status"] == "abstain" and reply["reason"] == "no_facts"
    assert reply["message"].endswith(cg.CONSULT)


def test_missing_or_empty_intents_table_disables_chips_but_not_answers(tmp_path, caplog):
    (tmp_path / "entities.json").write_text(json.dumps({"diseases": ["asthma"]}), encoding="utf-8")
    assert cg.ChatBotGraph.load_availability(tmp_path / "entities.json") == {}
    assert cg.ChatBotGraph.load_availability(tmp_path / "missing.json") == {}
    bot, _ = make_bot(availability={})
    reply = bot.respond("what causes asthma?")
    assert reply["status"] == "answer" and reply["options"] == []


def test_the_shipped_dictionary_lists_intents_for_every_disease():
    table = cg.ChatBotGraph.load_availability()
    assert set(table) == set(CLASSIFIER.disease_words)


def test_list_answers_carry_bullet_items():
    bot, _ = make_bot(rows=[{"subject": "asthma", "value": "cough"}, {"subject": "asthma", "value": "wheeze"}])
    answer = bot.respond("what are the symptoms of asthma?")["answers"][0]
    assert answer["lead"] == "The symptoms of asthma include:"
    assert answer["items"] == ["cough", "wheeze"]
    assert answer["label"] == "Symptoms"


# D-022: readiness against the dictionary the API loaded.

SOURCE = {"sha256": "a" * 64, "diseases": 658}


class ReadinessDriver:
    """A driver whose single read returns fixed counts, or raises; records the query, parameters and access mode."""

    def __init__(self, diseases=658, matching=658, error=None):
        self.result = {"diseases": diseases, "matching": matching}
        self.error = error
        self.seen = {}

    def session(self, **kwargs):
        self.seen["session"] = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, parameters):
        if self.error:
            raise self.error
        self.seen.update(query=query, parameters=parameters)
        return SimpleNamespace(single=lambda strict: self.result)


def ready_bot(driver, source=SOURCE):
    bot = cg.ChatBotGraph.__new__(cg.ChatBotGraph)
    bot.searcher = AnswerSearcher(driver=driver)
    bot.source = source
    return bot


@pytest.mark.parametrize("diseases, matching, ready", [
    (658, 658, True),
    (0, 0, False),        # empty graph
    (657, 657, False),    # wrong size
    (658, 0, False),      # another CSV
    (658, 600, False),    # some diseases unstamped or from another CSV
])
def test_ready_only_when_every_disease_matches_the_dictionary(diseases, matching, ready):
    assert ready_bot(ReadinessDriver(diseases, matching)).ready()[0] is ready


def test_readiness_is_one_short_read_of_importer_owned_diseases():
    import neo4j
    from build_medicalgraph import OWNER
    driver = ReadinessDriver()
    ready_bot(driver).ready()
    assert driver.seen["parameters"] == {"owner": OWNER, "hash": "a" * 64}
    assert driver.seen["session"]["default_access_mode"] == neo4j.READ_ACCESS
    assert driver.seen["query"].timeout <= 1.0
    assert "count(CASE" in driver.seen["query"].text


def test_driver_failures_and_a_missing_source_are_not_ready():
    from neo4j.exceptions import ServiceUnavailable
    assert ready_bot(ReadinessDriver(error=ServiceUnavailable("down"))).ready() == (False, "graph unreachable")
    assert ready_bot(ReadinessDriver(), source=None).ready()[0] is False


def test_the_source_is_read_from_the_dictionary(tmp_path):
    assert cg.ChatBotGraph.load_source()["diseases"] == len(CLASSIFIER.disease_words)
    (tmp_path / "entities.json").write_text(json.dumps({"diseases": ["asthma"]}), encoding="utf-8")
    assert cg.ChatBotGraph.load_source(tmp_path / "entities.json") is None
    (tmp_path / "entities.json").write_text(json.dumps({"diseases": [], "source_sha256": "a" * 64}), encoding="utf-8")
    assert cg.ChatBotGraph.load_source(tmp_path / "entities.json") is None


def test_the_dictionary_is_read_once_at_start_so_two_versions_never_mix(monkeypatch):
    """D35: if the importer replaced entities.json between separate reads, the classifier, the suggestions and
    readiness could describe different dictionaries while /health said ok."""
    document = json.loads(cg.ENTITIES_PATH.read_text(encoding="utf-8"))
    reads = []
    monkeypatch.setattr(cg, "read_dictionary", lambda: reads.append(1) or document)
    monkeypatch.setattr(cg, "AnswerSearcher", lambda: SimpleNamespace())
    bot = cg.ChatBotGraph()
    assert reads == [1]
    assert bot.source["diseases"] == len(document["diseases"]) and bot.availability == document["intents"]
    assert set(bot.classifier.disease_words) <= set(document["diseases"])
