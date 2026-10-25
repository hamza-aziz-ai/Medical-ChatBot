import sys
from pathlib import Path

import pytest

import build_medicalgraph as builder
from chatbot_graph_logic import ABSTENTION

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_kg  # noqa: E402

CASES = evaluate_kg.load_cases()
LIST_FIELDS = {"symptoms", "cure_way"}
TEXT_FIELDS = {"description", "causes", "prevention"}


class FakeClassifier:
    def __init__(self, result):
        self.result = result

    def classify(self, question):
        return self.result


class FakeChatbot:
    def __init__(self, answer, classified):
        self.answer = answer
        self.classifier = FakeClassifier(classified)

    def chat_main(self, question):
        return self.answer


def test_case_ids_are_unique_and_include_abstentions():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))
    assert any(case.get("abstain") for case in CASES)
    assert all(case.get("abstain") or case.get("facts") for case in CASES)


@pytest.mark.parametrize("case", [case for case in CASES if case.get("facts")], ids=lambda case: case["id"])
def test_expected_facts_trace_to_validated_source_records(case):
    diseases = builder.load_dataset()["diseases"]
    for fact in case["facts"]:
        record = diseases[fact["disease"]]
        field, value = fact["field"], fact["value"]
        if field in LIST_FIELDS:
            assert value in (record[field] or [])
        elif field in TEXT_FIELDS:
            assert value in record[field]
        else:
            # Complications are linked in either direction.
            assert field == "accompany"
            assert value in (record["accompany"] or []) or fact["disease"] in (diseases[value]["accompany"] or [])


def test_baseline_counts_match_the_import_plan():
    dataset = builder.load_dataset()
    counts = evaluate_kg.import_counts(dataset, builder.graph_data(dataset))
    baseline = evaluate_kg.json.loads(evaluate_kg.BASELINE_PATH.read_text(encoding="utf-8"))
    assert counts == baseline["counts"]


CASE = {"id": "c", "question": "q", "intents": ["disease_cause"], "entities": {"a": ["disease"]},
        "facts": [{"disease": "a", "field": "causes", "value": "dust"}]}
CLASSIFIED = {"question_types": ["disease_cause"], "arguments": {"a": ["disease"]}}


@pytest.mark.parametrize("answer, classified, failures", [
    ("The possible causes of a are: dust", CLASSIFIED, []),
    ("The possible causes of a are: pollen", CLASSIFIED, ["fact_0"]),
    (ABSTENTION, CLASSIFIED, ["unexpected_abstention"]),
    ("The possible causes of a are: dust", {"question_types": ["disease_symptom"], "arguments": {"a": ["disease"]}}, ["intents"]),
    ("The possible causes of a are: dust", {"question_types": ["disease_cause"], "arguments": {"b": ["disease"]}}, ["entities"]),
])
def test_check_case_names_each_failed_check(answer, classified, failures):
    assert evaluate_kg.check_case(CASE, classified, answer) == failures


def test_abstention_cases_fail_when_the_bot_answers():
    case = {"id": "x", "question": "q", "abstain": True}
    assert evaluate_kg.check_case(case, {}, ABSTENTION) == []
    assert evaluate_kg.check_case(case, {}, "Some answer") == ["abstention"]


def test_report_carries_ids_and_counts_but_no_question_or_answer():
    counts = {"diseases": 1}
    report = evaluate_kg.evaluate([CASE], FakeChatbot("secret answer about pollen", CLASSIFIED), counts, {"counts": {"diseases": 2}})
    assert report["passed"] is False
    assert report["failures"] == [{"id": "c", "failed_checks": ["fact_0"]}]
    assert report["count_mismatches"] == ["diseases"]
    text = evaluate_kg.json.dumps(report)
    assert "secret" not in text and '"q"' not in text
