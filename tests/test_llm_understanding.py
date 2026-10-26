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


def test_the_set_is_byte_identical_to_the_frozen_hash():
    # .gitattributes keeps its line endings LF everywhere; any edit to the set needs a new, recorded freeze.
    protocol = (Path(__file__).resolve().parents[1] / "docs" / "pilot" / "LLM-UNDERSTANDING.md").read_text(encoding="utf-8")
    assert f"SHA-256 `{u.set_digest()}`" in protocol


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


def replying(text, seconds=0.0):
    def chat(messages):
        assert messages[0]["content"] == u.SYSTEM_PROMPT
        return text, "gpt-oss:120b"
    return chat


def test_candidates_come_from_the_rules_matching_typed_by_selection_or_topic(bot):
    found, ambiguous = u.candidates_for(bot, "what are the symptoms of anemia", None, [])
    assert {(c["name"], c["type"]) for c in found} == {("anemia", "disease"), ("anemia", "symptom")} and not ambiguous
    found, _ = u.candidates_for(bot, "what are the symptoms of anemia", None, [{"name": "anemia", "type": "symptom"}])
    assert [(c["name"], c["type"], c["source"]) for c in found] == [("anemia", "symptom", "mention")]
    found, _ = u.candidates_for(bot, "what causes it?", ASTHMA, [])
    assert [(c["id"], c["name"], c["source"]) for c in found] == [("e1", "asthma", "topic")]
    found, _ = u.candidates_for(bot, "what causes brain worms", None, [])
    assert found == []


def test_a_valid_reply_becomes_a_frame_built_from_candidates(bot):
    result = u.ask_model(bot, "what causes asthma", None, [], replying('{"decision": "answer", "intents": [["disease_cause", "e1"]]}'))
    assert result["error"] is None
    assert u.normalise(result["frame"]) == u.normalise(answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA))
    declined = u.ask_model(bot, "how long does gout last", None, [], replying('{"decision": "unsupported", "intents": []}'))
    assert declined["frame"]["decision"] == "unsupported" and declined["frame"]["topic_out"] == GOUT


@pytest.mark.parametrize("question, reply, error", [
    ("what causes asthma", "Sure! Here you go: {}", "not a JSON object"),
    ("what causes asthma", '```json\n{"decision": "answer", "intents": [["disease_cause", "e1"]]}\n```', "not a JSON object"),
    ("what causes asthma", '{"decision": "answer", "intents": [["disease_cause", "e1"]], "note": "x"}', "wrong fields"),
    ("what causes asthma", '{"decision": "answer", "intents": [["disease_cause", "gout"]]}', "unknown intent or candidate"),
    ("what causes asthma", '{"decision": "answer", "intents": [["write_query", "e1"]]}', "unknown intent or candidate"),
    ("what causes asthma", '{"decision": "answer", "intents": [["disease_last_time", "e1"]]}', "supported intents only"),
    ("what causes asthma", '{"decision": "answer", "intents": []}', "supported intents only"),
    ("what causes asthma", '{"decision": "answer", "intents": [["symptom_disease", "e1"]]}', "type differ"),
    ("what are the symptoms of anemia and which diseases cause anemia",
     '{"decision": "answer", "intents": [["disease_symptom", "e1"], ["symptom_disease", "e2"]]}', "skip a confirmation"),
])
def test_unusable_replies_are_counted_never_repaired(bot, question, reply, error):
    result = u.ask_model(bot, question, None, [], replying(reply))
    assert result["frame"] is None and error in result["error"]


def test_slow_or_failed_calls_are_failures_not_retries(bot, monkeypatch):
    calls = []

    def failing(messages):
        calls.append(1)
        raise OSError("timed out")

    assert u.ask_model(bot, "what causes asthma", None, [], failing)["error"] == "timeout" and calls == [1]
    clock = iter([0.0, 2.5, 2.5])
    monkeypatch.setattr(u.time, "perf_counter", lambda: next(clock))
    slow = u.ask_model(bot, "what causes asthma", None, [], replying('{"decision": "answer", "intents": [["disease_cause", "e1"]]}'))
    assert slow["error"] == "timeout"


def test_configurations_differ_only_in_how_they_use_the_model():
    rules = {**other("unsupported", None), "reason": "no_entity"}
    model = {"frame": answer([("disease_cause", "asthma")], [ASTHMA], ASTHMA)}
    failed = {"frame": None}
    assert u.configured("validated model", rules, failed, ASTHMA)["decision"] == "invalid"
    assert u.configured("model plus fallback", rules, failed, None) is rules
    assert u.configured("rules-first", rules, model, None) is model["frame"]       # no_entity: the model is asked
    typo = {**other("clarify", None), "reason": "possible_typo"}
    assert u.configured("rules-first", typo, model, None) is typo                    # every other rule result stands


def test_the_bar_fails_on_any_new_wrong_subject_answer_and_measures_the_worst_run():
    def row(correct, unsafe, safety=False, category="paraphrase"):
        return {"id": "a", "turn": 0, "mode": "isolated", "split": "test", "category": category, "safety": safety,
                "correct": correct, "unsafe": unsafe, "got": other("answer", None)}

    rules = [row(False, False)]
    good, bad = [row(True, False)], [row(False, True)]
    calls = [{"error": None, "seconds": 0.5, "no_entity": False}] * 100
    result, reliability = u.evaluate(rules, {"validated model": [good, good, bad], "model plus fallback": [good] * 3,
                                             "rules-first": [rules] * 3}, calls)
    assert not result["validated model"]["gates"]["safety"] and result["validated model"]["gain_points"] == 0
    assert result["model plus fallback"]["gates"] == {"safety": True, "quality": True, "reliability": True, "latency": True}
    assert reliability["p95"] == 0.5 and reliability["valid"] == 100


def test_the_frozen_prompt_is_the_one_in_the_protocol():
    protocol = (Path(__file__).resolve().parents[1] / "docs" / "pilot" / "LLM-UNDERSTANDING.md").read_text(encoding="utf-8")
    assert f"prompt SHA-256 `{u.prompt_digest()}`" in protocol


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
