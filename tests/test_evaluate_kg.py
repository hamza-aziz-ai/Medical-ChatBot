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


def small_plan(tmp_path):
    path = tmp_path / "medical.csv"
    path.write_text(
        "S.No.,Name,Description,Prevention,Causes,Symptoms,Accompany,Cure Department,Cure Way\n"
        "0,a,d,p,c,\"['cough']\",\"['b']\",\"['internal medicine', 'respiratory']\",\"['rest']\"\n"
        "1,b,d,p,c,\"['fever']\",\"[]\",\"['internal medicine']\",\"['rest']\"\n",
        encoding="utf-8",
    )
    dataset = builder.load_dataset(path)
    plan = builder.graph_data(dataset)
    return plan, builder.entities_document(dataset, plan)


def clean_graph(plan):
    """Query results describing a graph that matches the plan exactly."""
    owner = builder.OWNER
    nodes = [{"labels": ["Disease"], "properties": dict(row["properties"], name=row["name"], owner=owner)} for row in plan["diseases"]]
    nodes += [{"labels": ["Symptom"], "properties": {"name": n, "owner": owner}} for n in plan["symptoms"]]
    nodes += [{"labels": ["Department"], "properties": {"name": n, "owner": owner}} for n in plan["departments"]]
    relationships = [
        {"type": rel, "start_labels": [evaluate_kg.RELATIONSHIPS[rel][0]], "start": start,
         "end_labels": [evaluate_kg.RELATIONSHIPS[rel][1]], "end": end,
         "properties": {"name": evaluate_kg.RELATIONSHIPS[rel][2], "owner": owner}}
        for rel, pairs in plan["edges"].items() for start, end in pairs
    ]
    zero = [{"c": 0}]
    return {
        evaluate_kg.OWNED_NODES: nodes,
        evaluate_kg.OWNED_RELATIONSHIPS: relationships,
        evaluate_kg.FOREIGN_RELATIONSHIPS_ON_OWNED: zero,
        evaluate_kg.OWNED_RELATIONSHIPS_LEAVING: zero,
        evaluate_kg.UNRELATED_NODES: [{"c": 3}],
        evaluate_kg.SELF_LOOPS: zero,
        evaluate_kg.DEPARTMENT_CYCLES: zero,
        evaluate_kg.ISOLATED: [],
        evaluate_kg.CONSTRAINTS: [{"labelsOrTypes": [label], "properties": ["name"], "type": "UNIQUENESS"} for label in evaluate_kg.LABELS],
    }


def run_checks(plan, dictionary, results):
    from conftest import FakeDriver
    return evaluate_kg.integrity_checks(FakeDriver(results=results), plan, dictionary)


def test_matching_graph_passes_and_reports_unrelated_data(tmp_path):
    plan, dictionary = small_plan(tmp_path)
    counts, failures = run_checks(plan, dictionary, clean_graph(plan))
    assert failures == []
    # 2 symptoms, 1 complication, 2 disease departments, 1 department hierarchy.
    assert counts["relationships"] == 6 and counts["unrelated_nodes"] == 3


def drop_edge(g):
    g[evaluate_kg.OWNED_RELATIONSHIPS].pop()


def duplicate_edge(g):
    g[evaluate_kg.OWNED_RELATIONSHIPS].append(g[evaluate_kg.OWNED_RELATIONSHIPS][0])


def wrong_direction(g):
    edge = g[evaluate_kg.OWNED_RELATIONSHIPS][0]
    edge["start"], edge["end"] = edge["end"], edge["start"]


def string_row_number(g):
    disease = next(n for n in g[evaluate_kg.OWNED_NODES] if n["labels"] == ["Disease"])
    disease["properties"]["source_rows"] = ["1"]


@pytest.mark.parametrize("corrupt, failure", [
    (drop_edge, "missing_relationships"),
    (duplicate_edge, "extra_relationships"),
    (wrong_direction, "missing_relationships"),
    (lambda g: g[evaluate_kg.OWNED_RELATIONSHIPS][0]["properties"].update(owner="someone"), "relationship_properties"),
    (string_row_number, "node_properties"),
    (lambda g: g[evaluate_kg.OWNED_NODES].append({"labels": ["Symptom"], "properties": {"name": "ghost", "owner": builder.OWNER}}), "extra_nodes"),
    (lambda g: g[evaluate_kg.OWNED_NODES].append(dict(g[evaluate_kg.OWNED_NODES][0])), "duplicate_nodes"),
    (lambda g: g[evaluate_kg.OWNED_NODES][0].update(labels=["Disease", "Symptom"]), "node_labels"),
    (lambda g: g.update({evaluate_kg.SELF_LOOPS: [{"c": 1}]}), "self_loops"),
    (lambda g: g.update({evaluate_kg.DEPARTMENT_CYCLES: [{"c": 2}]}), "department_cycles"),
    (lambda g: g.update({evaluate_kg.FOREIGN_RELATIONSHIPS_ON_OWNED: [{"c": 1}]}), "foreign_relationships_on_owned_nodes"),
    (lambda g: g.update({evaluate_kg.OWNED_RELATIONSHIPS_LEAVING: [{"c": 1}]}), "owned_relationships_leaving_snapshot"),
    (lambda g: g.update({evaluate_kg.ISOLATED: [{"labels": ["Symptom"], "c": 1}]}), "isolated_other_nodes"),
    (lambda g: g[evaluate_kg.CONSTRAINTS].pop(), "missing_constraints"),
])
def test_each_planted_corruption_is_caught(tmp_path, corrupt, failure):
    plan, dictionary = small_plan(tmp_path)
    graph = clean_graph(plan)
    corrupt(graph)
    assert failure in run_checks(plan, dictionary, graph)[1]


def test_isolated_disease_is_reported_not_failed(tmp_path):
    plan, dictionary = small_plan(tmp_path)
    graph = clean_graph(plan)
    graph[evaluate_kg.ISOLATED] = [{"labels": ["Disease"], "c": 1}]
    counts, failures = run_checks(plan, dictionary, graph)
    assert failures == [] and counts["isolated_diseases"] == 1


def test_stale_dictionary_fails(tmp_path):
    plan, dictionary = small_plan(tmp_path)
    assert "dictionary" in run_checks(plan, dict(dictionary, symptoms=["cough"]), clean_graph(plan))[1]
    assert "dictionary" in run_checks(plan, dict(dictionary, source_sha256="0" * 64), clean_graph(plan))[1]


def test_report_carries_ids_and_counts_but_no_question_or_answer():
    counts = {"diseases": 1}
    report = evaluate_kg.evaluate([CASE], FakeChatbot("secret answer about pollen", CLASSIFIED), counts, {"counts": {"diseases": 2}})
    assert report["passed"] is False
    assert report["failures"] == [{"id": "c", "failed_checks": ["fact_0"]}]
    assert report["count_mismatches"] == ["diseases"]
    text = evaluate_kg.json.dumps(report)
    assert "secret" not in text and '"q"' not in text
