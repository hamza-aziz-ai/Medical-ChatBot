"""Behavioural and source-faithfulness evaluation of the imported knowledge graph.

Runs eval/cases.jsonl through the real runtime against a graph built by build_medicalgraph.py and
compares the import counts with the reviewed eval/baseline.json. This checks that answers match the
source records; it does not measure medical or diagnostic accuracy.

The report holds counts, case IDs, check names, hashes and versions only: never a question or an answer.
Usage: python scripts/evaluate_kg.py [report.json]
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import build_medicalgraph as builder  # noqa: E402

CASES_PATH = ROOT / "eval" / "cases.jsonl"
BASELINE_PATH = ROOT / "eval" / "baseline.json"

# The graph contract, stated independently of the importer so the check can catch a shared mistake:
# relationship type -> (start label, end label, its name property).
RELATIONSHIPS = {
    "has_symptom": ("Disease", "Symptom", "symptom"),
    "accompany_with": ("Disease", "Disease", "complication"),
    "disease_belongs_to": ("Disease", "Department", "department"),
    "belongs_to": ("Department", "Department", "belong"),
}
LABELS = ("Disease", "Symptom", "Department")

# Every query is scoped to the importer's own snapshot; unrelated data in the database is only counted.
OWNED_NODES = "MATCH (n {owner: $owner}) RETURN labels(n) AS labels, properties(n) AS properties"
OWNED_RELATIONSHIPS = (
    "MATCH (a {owner: $owner})-[r]->(b {owner: $owner}) "
    "RETURN type(r) AS type, labels(a) AS start_labels, a.name AS start, labels(b) AS end_labels, b.name AS end, properties(r) AS properties"
)
FOREIGN_RELATIONSHIPS_ON_OWNED = "MATCH (n {owner: $owner})-[r]-() WHERE r.owner IS NULL OR r.owner <> $owner RETURN count(r) AS c"
OWNED_RELATIONSHIPS_LEAVING = (
    "MATCH (a)-[r {owner: $owner}]->(b) "
    "WHERE a.owner IS NULL OR a.owner <> $owner OR b.owner IS NULL OR b.owner <> $owner RETURN count(r) AS c"
)
UNRELATED_NODES = "MATCH (n) WHERE n.owner IS NULL OR n.owner <> $owner RETURN count(n) AS c"
SELF_LOOPS = "MATCH (a {owner: $owner})-[r {owner: $owner}]->(a) RETURN count(r) AS c"
DEPARTMENT_CYCLES = "MATCH p = (d:Department {owner: $owner})-[:belongs_to*1..50]->(d) RETURN count(p) AS c"
ISOLATED = "MATCH (n {owner: $owner}) WHERE NOT (n)--() RETURN labels(n) AS labels, count(n) AS c"
CONSTRAINTS = "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type RETURN labelsOrTypes, properties, type"


def load_cases(path=CASES_PATH):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def import_counts(dataset, data):
    return {
        "diseases": len(data["diseases"]),
        "quarantined_names": len(dataset["quarantined_names"]),
        "field_issues": len(dataset["field_issues"]),
        "symptoms": len(data["symptoms"]),
        "departments": len(data["departments"]),
        "unresolved_links": len(data["unresolved"]),
        "self_companions": len(data["self_companions"]),
        "repeated_departments": len(data["repeated_departments"]),
        **{f"{name}_relationships": len(pairs) for name, pairs in data["edges"].items()},
    }


def same(a, b):
    """Equal in value and in type, recursively (so 1 != 1.0 and "1" != 1)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def integrity_checks(driver, plan, dictionary, owner=builder.OWNER, database_name=None):
    """Compare the importer-owned graph with the plan and check its invariants. Returns (counts, failures)."""
    import collections

    def rows(query):
        records, _, _ = driver.execute_query(query, parameters_={"owner": owner}, database_=database_name)
        return [record.data() for record in records]

    def count(query):
        return rows(query)[0]["c"]

    failures, counts = [], {}

    # Nodes: exactly one expected label each, names as planned, properties equal in value and type.
    expected_nodes = {("Disease", row["name"]): dict(row["properties"], name=row["name"], owner=owner) for row in plan["diseases"]}
    for label, key in (("Symptom", "symptoms"), ("Department", "departments")):
        expected_nodes.update({(label, name): {"name": name, "owner": owner} for name in plan[key]})
    seen = collections.Counter()
    live_sources = set()
    bad_labels = wrong_properties = 0
    for row in rows(OWNED_NODES):
        if len(row["labels"]) != 1 or row["labels"][0] not in LABELS:
            bad_labels += 1
            continue
        key = (row["labels"][0], row["properties"].get("name"))
        seen[key] += 1
        if key[0] == "Disease":
            live_sources.add(row["properties"].get("source_sha256"))
        if key in expected_nodes and not same(row["properties"], expected_nodes[key]):
            wrong_properties += 1
    counts["nodes"] = sum(seen.values())
    for name, value in (
        ("node_labels", bad_labels),
        ("missing_nodes", len(expected_nodes.keys() - seen.keys())),
        ("extra_nodes", len(seen.keys() - expected_nodes.keys())),
        ("duplicate_nodes", sum(1 for c in seen.values() if c > 1)),
        ("node_properties", wrong_properties),
    ):
        counts[name] = value
        if value:
            failures.append(name)

    # Relationships: type, direction, endpoint labels, properties and multiplicity as planned.
    expected_edges = collections.Counter(
        (rel, RELATIONSHIPS[rel][0], start, RELATIONSHIPS[rel][1], end)
        for rel, pairs in plan["edges"].items() for start, end in pairs
    )
    actual_edges = collections.Counter()
    wrong_properties = 0
    for row in rows(OWNED_RELATIONSHIPS):
        actual_edges[(row["type"], first(row["start_labels"]), row["start"], first(row["end_labels"]), row["end"])] += 1
        expected_name = RELATIONSHIPS.get(row["type"], (None, None, None))[2]
        if not same(row["properties"], {"name": expected_name, "owner": owner}):
            wrong_properties += 1
    counts["relationships"] = sum(actual_edges.values())
    for name, value in (
        ("missing_relationships", sum((expected_edges - actual_edges).values())),
        ("extra_relationships", sum((actual_edges - expected_edges).values())),
        ("relationship_properties", wrong_properties),
    ):
        counts[name] = value
        if value:
            failures.append(name)

    # Ownership boundary and graph invariants, checked independently of the plan.
    for name, query in (
        ("foreign_relationships_on_owned_nodes", FOREIGN_RELATIONSHIPS_ON_OWNED),
        ("owned_relationships_leaving_snapshot", OWNED_RELATIONSHIPS_LEAVING),
        ("self_loops", SELF_LOOPS),
        ("department_cycles", DEPARTMENT_CYCLES),
    ):
        counts[name] = count(query)
        if counts[name]:
            failures.append(name)
    counts["unrelated_nodes"] = count(UNRELATED_NODES)

    # A disease whose relationship fields were all quarantined may stand alone; other labels may not.
    isolated = {first(row["labels"]): row["c"] for row in rows(ISOLATED)}
    counts["isolated_diseases"] = isolated.pop("Disease", 0)
    counts["isolated_other_nodes"] = sum(isolated.values())
    if counts["isolated_other_nodes"]:
        failures.append("isolated_other_nodes")

    constraints = {(tuple(row["labelsOrTypes"] or ()), tuple(row["properties"] or ()), row["type"]) for row in rows(CONSTRAINTS)}
    counts["missing_constraints"] = sum(1 for label in LABELS if ((label,), ("name",), "UNIQUENESS") not in constraints)
    if counts["missing_constraints"]:
        failures.append("missing_constraints")

    # The classifier's dictionary must describe both the plan and the live graph, from the same source.
    live_names = collections.defaultdict(list)
    for label, name in seen:
        live_names[label].append(name)
    planned_names = {"Disease": [row["name"] for row in plan["diseases"]], "Symptom": plan["symptoms"], "Department": plan["departments"]}
    dictionary_ok = live_sources <= {dictionary.get("source_sha256")} and all(
        sorted(names[label]) == dictionary.get(key)
        for names in (live_names, planned_names)
        for label, key in (("Disease", "diseases"), ("Symptom", "symptoms"), ("Department", "departments"))
    )
    if not dictionary_ok:
        failures.append("dictionary")
    return counts, failures


def chip_consistency(searcher, dictionary):
    """Every intent the dictionary lists for a disease must answer on the live graph, and no other may.

    Suggestion chips come from that list, so a mismatch would offer a question that gets "nothing recorded".
    """
    from question_parser import QuestionParser

    listed = dictionary.get("intents") or {}
    mismatches = 0
    for disease in dictionary.get("diseases", []):
        for intent in DISEASE_INTENTS:
            sqls = [{"question_type": intent, "sql": QuestionParser.sql_transfer(intent, [disease])}]
            if bool(searcher.search_structured(sqls)) != (intent in listed.get(disease, ())):
                mismatches += 1
    return {"diseases": len(listed), "mismatches": mismatches}


DISEASE_INTENTS = ("disease_symptom", "disease_cause", "disease_prevention", "disease_cure_way",
                   "disease_accompany", "disease_description")


def first(labels):
    return labels[0] if labels else None


def check_case(case, reply):
    """Names of the checks this case failed; empty when it passed.

    Intents and entities are read from the reply's own interpretation, so a follow-up answered about the
    wrong subject fails even when its wording looks right.
    """
    failures = []
    interpretation = reply.get("interpretation") or {}
    intents = [item["intent"] for item in interpretation.get("intents", [])]
    entities = {item["name"]: sorted(item["types"]) for item in interpretation.get("entities", [])}
    if "intents" in case and sorted(case["intents"]) != sorted(intents):
        failures.append("intents")
    if "entities" in case and case["entities"] != entities:
        failures.append("entities")
    expected_status = "abstain" if case.get("abstain") else case.get("status", "answer")
    if reply.get("status") != expected_status:
        failures.append("abstention" if expected_status == "abstain" else f"status_{reply.get('status')}")
    elif expected_status == "answer":
        answer = reply.get("message", "")
        for index, fact in enumerate(case.get("facts", [])):
            if fact["disease"] not in answer or fact["value"] not in answer:
                failures.append(f"fact_{index}")
    return failures


def evaluate(cases, chatbot, counts, baseline):
    results, latencies = [], []
    for case in cases:
        started = time.perf_counter()
        reply = chatbot.respond(case["question"], topic=case.get("topic"), selections=case.get("selections", ()))
        latencies.append((time.perf_counter() - started) * 1000)
        failures = check_case(case, reply)
        results.append({"id": case["id"], "failed_checks": failures})

    count_mismatches = sorted(key for key in baseline["counts"] if counts.get(key) != baseline["counts"][key])
    failed = [result for result in results if result["failed_checks"]]
    return {
        "passed": not failed and not count_mismatches,
        "cases": len(results),
        "cases_passed": len(results) - len(failed),
        "abstention_cases": sum(1 for case in cases if case.get("abstain")),
        "failures": failed,
        "counts": counts,
        "count_mismatches": count_mismatches,
        "latency_ms": {"median": round(statistics.median(latencies), 1), "max": round(max(latencies), 1)} if latencies else {},
    }


def main(report_path=None):
    from chatbot_graph_logic import ChatBotGraph
    import database

    dataset = builder.load_dataset()
    data, document = builder.plan(dataset)
    counts = import_counts(dataset, data)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    dictionary = json.loads(builder.ENTITIES_PATH.read_text(encoding="utf-8"))

    chatbot = ChatBotGraph()
    try:
        driver = chatbot.searcher.driver
        report = evaluate(load_cases(), chatbot, counts, baseline)
        integrity_counts, integrity_failures = integrity_checks(driver, data, dictionary, database_name=database.database_name())
        chips = chip_consistency(chatbot.searcher, dictionary)
        if chips["mismatches"] or chips["diseases"] != len(dictionary.get("diseases", [])):
            integrity_failures.append("chip_consistency")
        # D-023: the shipped dictionary is exactly the one this plan publishes, and the API accepts the imported graph.
        if dictionary != document:
            integrity_failures.append("dictionary_plan")
        if not chatbot.ready()[0]:
            integrity_failures.append("readiness")
        integrity_counts["chip_mismatches"] = chips["mismatches"]
        report["integrity"] = {"failures": integrity_failures, "counts": integrity_counts}
        report["passed"] = report["passed"] and not integrity_failures
        report["server"] = driver.get_server_info().agent
    finally:
        chatbot.searcher.close()

    report["source_sha256"] = dataset["source_sha256"]
    report["git_sha"] = os.environ.get("GITHUB_SHA", "local")

    text = json.dumps(report, indent=2)
    if report_path:
        Path(report_path).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
