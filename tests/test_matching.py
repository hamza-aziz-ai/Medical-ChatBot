"""Step 2 of D-015: sourced aliases and confirmed typo suggestions."""
import json

import pytest

import chatbot_graph_logic as cg
import question_classifier as qc
from answer_searcher import AnswerSearcher
from conftest import FakeDriver
from question_parser import QuestionParser

CLASSIFIER = qc.QuestionClassifier()

# Reviewed examples that set TYPO_CUTOFF: every misspelling must find its name, no unrelated word may find any.
MISSPELLINGS = {"asthama": "asthma", "migrane": "migraine", "anemea": "anemia", "pertusis": "pertussis",
                "diarhea": "diarrhea", "hypothyroidsm": "hypothyroidism", "tiredniss": "tiredness"}
UNRELATED = ["covid", "flu", "hello", "zzyzx", "children", "pregnancy", "cancer"]


def make_bot(classifier=CLASSIFIER, rows=None):
    driver = FakeDriver(rows=rows if rows is not None else [{"subject": "pertussis", "value": "chest tightness"}])
    bot = cg.ChatBotGraph.__new__(cg.ChatBotGraph)
    bot.classifier, bot.parser, bot.availability = classifier, QuestionParser(), {}
    bot.searcher = AnswerSearcher(driver=driver)
    return bot, driver


def test_every_shipped_alias_is_sourced_and_points_at_a_real_entry():
    entries = json.loads(qc.ALIASES_PATH.read_text(encoding="utf-8"))["aliases"]
    names = {"disease": set(CLASSIFIER.disease_words), "symptom": set(CLASSIFIER.symptom_words)}
    seen = set()
    for entry in entries:
        assert entry["source"].startswith("https://medlineplus.gov/")
        assert entry["name"] in names[entry["type"]]
        assert entry["alias"] not in CLASSIFIER.word_type_dictionary
        assert entry["alias"] not in seen
        seen.add(entry["alias"])
    assert set(CLASSIFIER.aliases) == seen


def test_invalid_alias_entries_are_skipped(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"aliases": [
        {"alias": "good one", "name": "asthma", "type": "disease"},
        {"alias": "wrong type", "name": "asthma", "type": "symptom"},
        {"alias": "no such target", "name": "not a disease", "type": "disease"},
        {"alias": "asthma", "name": "asthma", "type": "disease"},
    ]}), encoding="utf-8")
    loaded = qc.load_aliases({"disease": {"asthma"}, "symptom": set()}, path)
    assert loaded == {"good one": [("asthma", "disease")]}
    assert qc.load_aliases({}, tmp_path / "missing.json") == {}


def test_an_alias_answers_as_its_entry_and_says_so():
    bot, _ = make_bot()
    reply = bot.respond("What are the symptoms of whooping cough?")
    assert reply["status"] == "answer"
    assert reply["interpretation"]["entities"] == [{"name": "pertussis", "types": ["disease"]}]
    assert reply["interpretation"]["aliases"] == [{"alias": "whooping cough", "name": "pertussis"}]


def test_an_alias_with_several_meanings_asks_which_one():
    classifier = qc.QuestionClassifier()
    classifier.aliases = {"lung trouble": [("asthma", "disease"), ("pertussis", "disease")]}
    classifier.region_tree = classifier.build_acyclic_tree(list(classifier.region_words | set(classifier.aliases)))
    bot, driver = make_bot(classifier)
    reply = bot.respond("what causes lung trouble?")
    assert reply["status"] == "clarify" and reply["reason"] == "ambiguous_alias"
    assert [o["question"] for o in reply["options"]] == ["what causes asthma?", "what causes pertussis?"]
    assert driver.calls == []


@pytest.mark.parametrize("word, name", MISSPELLINGS.items())
def test_misspellings_are_offered_for_confirmation_never_applied(word, name):
    bot, driver = make_bot()
    reply = bot.respond(f"what causes {word}?")
    assert reply["status"] == "clarify" and reply["reason"] == "possible_typo"
    assert f"what causes {name}?" in [o["question"] for o in reply["options"]]
    assert driver.calls == []


@pytest.mark.parametrize("word", UNRELATED)
def test_unrelated_words_get_no_suggestion(word):
    bot, driver = make_bot()
    reply = bot.respond(f"what causes {word}?")
    assert reply["status"] == "abstain" and reply["reason"] == "no_entity"
    assert driver.calls == []


def test_a_confirmed_suggestion_answers_the_corrected_question():
    bot, driver = make_bot(rows=[{"subject": "asthma", "value": "dust"}])
    option = bot.respond("What causes ASTHAMA?")["options"][0]
    assert option["question"] == "What causes asthma?"
    assert bot.respond(option["question"])["status"] == "answer" and driver.calls


def test_suggestions_keep_the_rest_of_the_question():
    bot, _ = make_bot()
    options = bot.respond("how do i prevent migrane at night?")["options"]
    assert options[0]["question"] == "how do i prevent migraine at night?"
