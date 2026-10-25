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
from chatbot_graph_logic import ABSTENTION  # noqa: E402

CASES_PATH = ROOT / "eval" / "cases.jsonl"
BASELINE_PATH = ROOT / "eval" / "baseline.json"


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
    }


def check_case(case, classified, answer):
    """Names of the checks this case failed; empty when it passed."""
    failures = []
    if "intents" in case and sorted(case["intents"]) != sorted(classified.get("question_types", [])):
        failures.append("intents")
    if "entities" in case and case["entities"] != {name: sorted(kinds) for name, kinds in classified.get("arguments", {}).items()}:
        failures.append("entities")
    if case.get("abstain"):
        if answer != ABSTENTION:
            failures.append("abstention")
    elif answer == ABSTENTION:
        failures.append("unexpected_abstention")
    else:
        for index, fact in enumerate(case.get("facts", [])):
            if fact["disease"] not in answer or fact["value"] not in answer:
                failures.append(f"fact_{index}")
    return failures


def evaluate(cases, chatbot, counts, baseline):
    results, latencies = [], []
    for case in cases:
        started = time.perf_counter()
        answer = chatbot.chat_main(case["question"])
        latencies.append((time.perf_counter() - started) * 1000)
        failures = check_case(case, chatbot.classifier.classify(case["question"]), answer)
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
    data = builder.graph_data(dataset)
    counts = import_counts(dataset, data)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    chatbot = ChatBotGraph()
    try:
        driver = chatbot.searcher.driver
        records, _, _ = driver.execute_query(
            "MATCH (n:Disease {owner: $owner}) RETURN count(n) AS n", parameters_={"owner": builder.OWNER},
            database_=database.database_name(),
        )
        counts["graph_diseases"] = records[0]["n"]
        report = evaluate(load_cases(), chatbot, counts, baseline)
        report["server"] = driver.get_server_info().agent
    finally:
        chatbot.searcher.close()

    if counts["graph_diseases"] != counts["diseases"]:
        report["passed"] = False
        report["count_mismatches"].append("graph_diseases")
    report["source_sha256"] = dataset["source_sha256"]
    report["git_sha"] = os.environ.get("GITHUB_SHA", "local")

    text = json.dumps(report, indent=2)
    if report_path:
        Path(report_path).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
