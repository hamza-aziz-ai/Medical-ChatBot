"""The offline rewording generator (D-029) with a fake model: no network, no cloud calls."""
import importlib.util
import json
from pathlib import Path

import pytest

import answer_searcher
import text_format
import understanding
from question_classifier import QuestionClassifier

SPEC = importlib.util.spec_from_file_location("reword_answers", Path(__file__).resolve().parents[1] / "scripts" / "reword_answers.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)

VALUES = {("asthma", "disease_prevention"): ["daily prevention: 1. avoid allergens. 2, no pets indoors."]}
CLEAN = '{"adds": false, "omits": false, "contradicts": false, "reverses_cause": false, "changes_certainty": false, "changes_quantity": false}'


@pytest.fixture
def classifier():
    return QuestionClassifier()


def fake_model(monkeypatch, reword=lambda passage: passage, verdict=CLEAN):
    sent = []

    def chat(messages, url, model, timeout):
        sent.append(messages[0]["content"])
        payload = json.loads(messages[1]["content"])
        if messages[0]["content"] == r.REWORD_PROMPT:
            return json.dumps({"text": reword(payload["passage"])}), "m"
        return verdict, "m"

    monkeypatch.setattr(understanding, "chat", chat)
    return sent


def test_the_mechanical_filters_catch_what_they_can_and_pass_a_faithful_rewrite(classifier):
    source = "Avoid low-dose aspirin (less than 2 g daily) in asthma."
    assert r.mechanical(source, "Do not use low-dose aspirin (under 2 g daily) in asthma.", classifier) == []
    assert "numbers" in r.mechanical(source, "Avoid low-dose aspirin (less than 3 g daily) in asthma.", classifier)
    assert "negations" in r.mechanical(source, "Use low-dose aspirin (less than 2 g daily) in asthma.", classifier)
    assert "new_names" in r.mechanical(source, "Avoid low-dose aspirin (less than 2 g daily) in asthma and gout.", classifier)
    assert "length" in r.mechanical(source, "Avoid it.", classifier)


def test_a_malformed_or_failing_verifier_reply_fails(monkeypatch):
    fake_model(monkeypatch, verdict="not json")
    assert r.verify(r.Calls(5), "a", "b") == ["verifier_JSONDecodeError"]
    fake_model(monkeypatch, verdict='{"adds": true}')
    assert r.verify(r.Calls(5), "a", "b") == ["verifier_malformed"]
    fake_model(monkeypatch, verdict=CLEAN.replace('"omits": false', '"omits": true'))
    assert r.verify(r.Calls(5), "a", "b") == ["omits"]


def test_generation_writes_a_checked_candidate_with_its_identities_and_resumes(tmp_path, monkeypatch, classifier):
    monkeypatch.setattr(r, "OUT", tmp_path)
    sent = fake_model(monkeypatch, reword=lambda passage: passage.replace("allergens", "any allergens"))
    calls = r.Calls(10)
    r.generate(VALUES, calls, classifier)
    [path] = tmp_path.glob("*.json")
    candidate = json.loads(path.read_text(encoding="utf-8"))
    vals = VALUES[("asthma", "disease_prevention")]
    assert candidate["input_sha256"] == answer_searcher.digest(answer_searcher.canonical_input("asthma", "disease_prevention", vals))
    assert candidate["format_identity"] == text_format.FORMAT_IDENTITY
    assert candidate["sections"][0]["heading"] == "Daily prevention" and candidate["sections"][0]["items"][0] == "Avoid any allergens."
    assert candidate["output_sha256"] == answer_searcher.sections_digest(candidate["sections"]) and candidate["checks_passed"]
    assert calls.made == 3 and len(sent) == 3                               # two passages and one field check
    r.generate(VALUES, calls, classifier)
    assert calls.made == 3                                                  # same input, prompts and settings: resumed


def test_the_call_cap_stops_generation_before_it_is_exceeded(tmp_path, monkeypatch, classifier):
    monkeypatch.setattr(r, "OUT", tmp_path)
    fake_model(monkeypatch)
    calls = r.Calls(1)
    r.generate(VALUES, calls, classifier)
    assert calls.made == 1 and list(tmp_path.glob("*.json")) == []


def approve_setup(tmp_path, monkeypatch, classifier, verdict=CLEAN):
    monkeypatch.setattr(r, "OUT", tmp_path)
    fake_model(monkeypatch, verdict=verdict)
    r.generate(VALUES, r.Calls(10), classifier)
    [path] = tmp_path.glob("*.json")
    candidate = json.loads(path.read_text(encoding="utf-8"))
    store = tmp_path / "store.json"
    store.write_text('{"note": "n", "entries": []}', encoding="utf-8")
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"approved": [{k: candidate[k] for k in ("subject", "intent", "input_sha256", "output_sha256", "format_identity")}]}), encoding="utf-8")
    return path, candidate, store, decisions


def test_approval_publishes_exactly_what_was_reviewed_and_the_api_serves_it(tmp_path, monkeypatch, classifier):
    _, candidate, store, decisions = approve_setup(tmp_path, monkeypatch, classifier)
    assert r.approve(decisions, store) == 1
    loaded = answer_searcher.load_rewordings(store)
    assert loaded[("asthma", "disease_prevention")]["sections"] == candidate["sections"]


def test_approval_refuses_an_output_edited_after_review(tmp_path, monkeypatch, classifier):
    path, candidate, store, decisions = approve_setup(tmp_path, monkeypatch, classifier)
    candidate["sections"][0]["items"][0] = "Allergens are fine."
    path.write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(SystemExit, match="Refused"):
        r.approve(decisions, store)
    assert json.loads(store.read_text(encoding="utf-8"))["entries"] == []


def test_approval_refuses_a_field_that_failed_its_checks(tmp_path, monkeypatch, classifier):
    _, _, store, decisions = approve_setup(tmp_path, monkeypatch, classifier, verdict=CLEAN.replace('"adds": false', '"adds": true'))
    with pytest.raises(SystemExit, match="Refused"):
        r.approve(decisions, store)


def test_the_challenge_set_is_well_formed():
    rows = [json.loads(line) for line in r.CHALLENGES.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds = {row["kind"] for row in rows}
    assert {"control", "negation_flip", "cause_reversal", "quantity_change", "quantity_swap", "dropped_clause", "added_fact",
            "certainty_change"} == kinds
    assert all(row["source"] != row["rewrite"] or row["kind"] == "control" for row in rows) and len({row["id"] for row in rows}) == len(rows)
