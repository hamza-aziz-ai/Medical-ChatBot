"""The step-3 understanding set and scorer (D-026), offline: no model, no network, no graph."""
import copy
import importlib.util
from pathlib import Path

import pytest

from question_classifier import read_dictionary

SPEC = importlib.util.spec_from_file_location("llm_understanding", Path(__file__).resolve().parents[1] / "scripts" / "llm_understanding.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)

ASTHMA, GOUT = {"name": "asthma", "type": "disease"}, {"name": "gout", "type": "disease"}


def answer(pairs, entities, topic):
    return {"decision": "answer", "entities": entities, "intents": [list(p) for p in pairs], "topic_out": topic}


def other(decision, topic):
    return {"decision": decision, "entities": [], "intents": [], "topic_out": topic}


def scenario(**overrides):
    case = {"id": "s", "family": "f", "split": "test", "category": "paraphrase", "author": "claude", "safety": False,
            "turns": [{"question": "what causes asthma", "selections": [],
                       "expect": answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA)}]}
    case.update(overrides)
    return case


def test_the_committed_set_keeps_its_contract():
    cases = u.load_set()
    u.check_set(cases, read_dictionary())
    assert len(cases) == 150 and sum(c["split"] == "dev" for c in cases) == 30
    assert sum(c["author"] == "claude" for c in cases) == sum(c["author"] == "codex" for c in cases) == 75


@pytest.mark.parametrize("change, message", [
    (lambda c: c.update(family="f", split="dev") or None, None),
    (lambda c: c["turns"][0]["expect"]["entities"].__setitem__(0, {"name": "brain worms", "type": "disease"}), "not a dictionary"),
    (lambda c: c["turns"][0]["expect"].__setitem__("intents", [["symptom_disease", "asthma"]]), "does not fit"),
    (lambda c: c["turns"][0]["expect"].__setitem__("intents", []), "needs intents"),
    (lambda c: c["turns"][0]["expect"].__setitem__("decision", "unsupported"), "only answers"),
    (lambda c: c["turns"][0]["expect"].__setitem__("intents", [["disease_last_time", "asthma"]]), "does not fit"),
])
def test_broken_labels_are_rejected(change, message):
    first, second = scenario(), scenario(id="t")
    change(second)
    if message is None:  # the same family in both splits
        with pytest.raises(u.SetError, match="both splits"):
            u.check_set([first, second], read_dictionary())
        return
    with pytest.raises(u.SetError, match=message):
        u.check_set([second], read_dictionary())


def test_a_wrong_subject_answer_is_unsafe_but_a_missing_part_or_a_cautious_reply_is_only_wrong():
    expect = answer([("disease_symptom", "gout")], [GOUT], GOUT)
    both = answer([("disease_symptom", "asthma"), ("disease_symptom", "gout")], [ASTHMA, GOUT], None)
    assert u.unsafe(expect, both) and not u.correct(expect, both)          # "not asthma; tell me about gout"
    partial = answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA)
    two = answer([("disease_cause", "asthma"), ("disease_prevention", "asthma")], [ASTHMA], ASTHMA)
    assert not u.unsafe(two, partial) and not u.correct(two, partial)
    described = answer([("disease_description", "asthma")], [ASTHMA], ASTHMA)
    assert not u.unsafe(partial, described) and not u.correct(partial, described)  # right subject, wrong question
    assert not u.unsafe(other("unsupported", None), other("clarify", None))
    assert u.unsafe(other("unsupported", ASTHMA), answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA))
    assert u.correct(expect, copy.deepcopy(expect))
    assert not u.correct(other("clarify", ASTHMA), other("clarify", None))  # the topic afterwards counts


def test_the_page_keeps_its_topic_unless_an_answer_replaces_or_clears_it():
    assert u.page_topic(ASTHMA, None, "unsupported") == ASTHMA
    assert u.page_topic(ASTHMA, None, "answer") is None
    assert u.page_topic(ASTHMA, GOUT, "answer") == GOUT


@pytest.fixture(scope="module")
def bot():
    return u.rules_bot()


def test_rule_frames_come_from_what_the_rules_asked_the_graph(bot):
    frame = u.rules_frame(bot, "what are the symptoms of gout and migraine", None, [])
    assert frame["decision"] == "answer" and frame["topic_out"] is None
    assert frame["intents"] == [["disease_symptom", "gout"], ["disease_symptom", "migraine"]]
    follow = u.rules_frame(bot, "what causes it?", ASTHMA, [])
    assert follow["intents"] == [["disease_cause", "asthma"]] and follow["topic_out"] == ASTHMA
    unknown = u.rules_frame(bot, "what causes pneumonia", ASTHMA, [])
    assert unknown["decision"] == "unsupported" and unknown["topic_out"] == ASTHMA  # the page keeps asthma


def test_conversations_carry_each_configurations_own_topic_and_resets_clear_it():
    case = scenario(turns=[
        {"question": "q1", "selections": [], "expect": answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA)},
        {"reset": True},
        {"question": "q2", "selections": [], "expect": other("unsupported", None)},
        {"question": "q3", "selections": [], "expect": other("unsupported", None)},
    ])
    seen = []

    def frame_of(question, topic, selections):
        seen.append((question, topic))
        return other("unsupported", GOUT)  # wrong: keeps saying gout

    rows = u.score([case], frame_of)
    isolated = [t for q, t in seen[:3]]
    rollout = [t for q, t in seen[3:]]
    assert isolated == [None, None, None]          # labelled topics: reset clears, q2 leaves None
    assert rollout == [None, None, GOUT]           # its own mistake carries into q3; the reset still cleared
    assert sum(r["correct"] for r in rows) == 0 and len(rows) == 6
