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


# A-13: names that contain filler words or intent keywords are suggested whole, from the window that is the typo.

@pytest.mark.parametrize("question, expected", [
    ("what causes deep plam infection?", "what causes deep palm infection?"),
    ("what causes fcae of bruises?", "what causes face of bruises?"),
    ("what causes adbominal infection", "what causes abdominal infection"),
    ("could you please tell me what you know about the possible causes of deep plam infection?",
     "could you please tell me what you know about the possible causes of deep palm infection?"),
    ("what causes deep plam, infection?", "what causes deep palm infection?"),
    ("WHAT CAUSES   Deep Plam Infection", "WHAT CAUSES   deep palm infection"),
    ("(deep plam infection)", "(deep palm infection)"),
])
def test_names_with_filler_or_keywords_are_suggested_as_complete_questions(question, expected):
    bot, driver = make_bot()
    reply = bot.respond(question)
    assert reply["status"] == "clarify" and reply["reason"] == "possible_typo"
    assert expected in [o["question"] for o in reply["options"]]
    assert all(o["question"] != question for o in reply["options"])
    assert driver.calls == []


@pytest.mark.parametrize("question", [
    "what are the symptoms of pneumonia",  # pneumonia is quarantined; "of pneumonia" must not suggest "shock pneumonia"
    "what causes covid?", "who gets infections?", "what is the cure rate?", "how do i get better?",
    "is it dangerous?", "how long does flu last?", "can you tell me more?", "what should i do about it?",
])
def test_ordinary_questions_without_a_name_get_no_suggestion(question):
    bot, driver = make_bot()
    reply = bot.respond(question)
    assert reply["status"] == "abstain" and reply["options"] == [] and driver.calls == []


def test_known_names_and_follow_ups_never_reach_spelling_suggestions(monkeypatch):
    bot, _ = make_bot()
    monkeypatch.setattr(bot.classifier, "close_matches", lambda phrases: pytest.fail("fuzzy matching ran"))
    assert bot.respond("what causes deep palm infection?")["status"] == "answer"
    assert bot.respond("and what causes it?", topic={"name": "pertussis", "type": "disease"})["status"] == "answer"


def test_candidate_windows_are_deduplicated_in_order():
    bot, _ = make_bot()
    phrases = bot.unexplained_phrases("plam plam plam")
    assert phrases == ["plam plam plam", "plam plam", "plam"]
    assert "what causes" not in bot.unexplained_phrases("what causes plam")


def test_every_short_name_with_filler_or_keywords_survives_one_typo():
    """Grid: each name of up to 3 words that contains a filler word or an intent keyword, with two letters of its
    longest word swapped. Names whose typo still contains another known name take the entity path, not this one.
    Excluded: artefact names ending in punctuation ("hbv and hcv..."); the name is still offered, but the corrected
    question repeats the trailing dots."""
    bot, _ = make_bot()
    keywords = {w for phrase in CLASSIFIER.intent_keywords() for w in phrase.lower().split()}
    checked, missed, punctuated = 0, [], []
    for name in sorted(set(CLASSIFIER.disease_words) | set(CLASSIFIER.symptom_words)):
        words = name.split()
        if len(words) > 3 or not any(w in keywords or w in cg.FILLER for w in words):
            continue
        if name != name.strip(cg.PUNCTUATION):
            punctuated.append(name)
            continue
        longest = max(range(len(words)), key=lambda i: len(words[i]))
        if len(words[longest]) < 4:
            continue
        words[longest] = words[longest][0] + words[longest][2] + words[longest][1] + words[longest][3:]
        question = f"what causes {' '.join(words)}"
        if CLASSIFIER.check_medical(question.lower()):
            continue
        checked += 1
        if f"what causes {name}" not in [o["question"] for o in bot.respond(question)["options"]]:
            missed.append(name)
    assert checked >= 60
    assert missed == []
    assert len(punctuated) <= 5, punctuated


# A-14: a time budget on spelling suggestions, with safe partial results.

class StepClock:
    """Returns 0 for the first `free` readings, then a time far past any deadline."""

    def __init__(self, free):
        self.readings = 0
        self.free = free

    def __call__(self):
        self.readings += 1
        return 0.0 if self.readings <= self.free else 1000.0


def suggest(question, clock):
    bot, _ = make_bot()
    keywords = bot.keyword_words()
    return bot.classifier.close_matches(bot.unexplained_phrases(question), clock=clock,
                                        accept=lambda window, name: cg.edge_words_match(window, name, keywords))


def test_an_expired_budget_stops_before_any_window(caplog):
    caplog.set_level("INFO")
    assert suggest("what causes asthama", StepClock(free=1)) == []
    assert "stopped after 0 of" in caplog.text and "asthama" not in caplog.text


def test_reaching_the_deadline_exactly_stops_the_scan():
    deadline_hit = iter([0.0] + [qc.TYPO_BUDGET_SECONDS] * 50)
    assert suggest("what causes asthama", lambda: next(deadline_hit)) == []


def test_suggestions_found_before_the_budget_runs_out_are_kept():
    nonsense = " ".join(f"zq{i}x" for i in range(60))
    found = suggest(f"asthama {nonsense}", StepClock(free=5))
    assert [name for _, name in found] == ["asthma"]


def test_early_typos_of_one_two_or_three_words_are_reached_first():
    nonsense = " ".join(f"zq{i}x" for i in range(60))
    for typo, name in [("asthama", "asthma"), ("allergic asthama", "allergic asthma"), ("deep plam infection", "deep palm infection")]:
        found = suggest(f"{typo} {nonsense}", StepClock(free=5))
        assert name in [n for _, n in found], typo


def test_a_cut_short_scan_never_drops_question_words():
    # Only the first windows are tried: "causes adbominal infection" matches "abdominal infection" but would turn
    # the question into "what abdominal infection"; the edge-keyword rule refuses it.
    for free in range(1, 8):
        for window, name in suggest("what causes adbominal infection", StepClock(free=free)):
            assert cg.replace_phrase("what causes adbominal infection", window, name).startswith("what causes")


def test_windows_run_position_first():
    bot, _ = make_bot()
    assert bot.unexplained_phrases("aaa bbb ccc") == ["aaa bbb ccc", "aaa bbb", "aaa", "bbb ccc", "bbb", "ccc"]
