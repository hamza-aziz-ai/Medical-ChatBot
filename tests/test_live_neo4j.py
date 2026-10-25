"""Integration tests against a real, disposable Neo4j server.

They run only when NEO4J_TEST_URI and NEO4J_PASSWORD are set and NEO4J_TEST_ALLOW_WIPE=1,
because every test deletes all data in the target database. Never point them at a real database.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from neo4j.exceptions import ClientError

import build_medicalgraph as builder
import database
from answer_searcher import AnswerSearcher
from question_parser import TEMPLATES, QuestionParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_kg  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NEO4J_TEST_URI") and os.environ.get("NEO4J_PASSWORD") and os.environ.get("NEO4J_TEST_ALLOW_WIPE") == "1"),
    reason="live Neo4j tests need NEO4J_TEST_URI, NEO4J_PASSWORD and NEO4J_TEST_ALLOW_WIPE=1",
)

HEADER = "S.No.,Name,Description,Prevention,Causes,Symptoms,Accompany,Cure Department,Cure Way\n"


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", os.environ["NEO4J_TEST_URI"])
    with database.create_driver() as live:
        live.execute_query("MATCH (n) DETACH DELETE n")
        yield live


def scalar(driver, query, **params):
    records, _, _ = driver.execute_query(query, parameters_=params)
    return records[0][0]


def counts(driver):
    return (
        scalar(driver, "MATCH (n) RETURN count(n)"),
        scalar(driver, "MATCH ()-[r]->() RETURN count(r)"),
    )


def write_csv(tmp_path, name, rows):
    path = tmp_path / name
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def row(number, name, description="d", symptoms="['cough']", accompany="[]", cure_way="['rest']", department="['internal medicine', 'respiratory medicine']"):
    return f'{number},{name},{description},p,c,"{symptoms}","{accompany}","{department}","{cure_way}"\n'


def import_csv(driver, path):
    dataset = builder.load_dataset(path)
    data = builder.graph_data(dataset)
    assert builder.existing_conflicts(driver, dataset, data) == []
    builder.create_constraints(driver)
    with driver.session(database=database.database_name()) as session:
        session.execute_write(builder.write_graph, data)
    return dataset, data


def test_server_version_is_recorded(driver):
    records, _, _ = driver.execute_query("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS version")
    print("Neo4j under test:", [(r["name"], r["version"]) for r in records])
    assert records


def test_full_import_is_idempotent_and_constrained(driver, tmp_path, monkeypatch):
    target = tmp_path / "entities.json"
    monkeypatch.setattr(builder.stage_entities, "__defaults__", (target,))
    monkeypatch.setattr(builder.publish_entities, "__defaults__", (target,))

    assert builder.main() == 0
    first = counts(driver)
    assert builder.main() == 0
    assert counts(driver) == first
    assert scalar(driver, "MATCH (d:Disease) RETURN count(d)") == 658
    constraints = scalar(driver, "SHOW CONSTRAINTS YIELD labelsOrTypes RETURN collect(labelsOrTypes[0])")
    assert {"Disease", "Symptom", "Department"} <= set(constraints)
    assert target.exists()

    dataset = builder.load_dataset()
    integrity, failures = evaluate_kg.integrity_checks(driver, builder.graph_data(dataset), json.loads(target.read_text(encoding="utf-8")))
    assert failures == [], integrity


def test_integrity_check_passes_a_clean_import_and_catches_planted_damage(driver, tmp_path):
    path = write_csv(tmp_path, "a.csv", [
        row(0, "a", accompany="['a', 'b']", department="['oncology', 'oncology']"),
        row(1, "b", symptoms="['fever']"),
    ])
    import_csv(driver, path)
    driver.execute_query("CREATE (:Note {name: 'unrelated'})")
    dataset = builder.load_dataset(path)
    plan = builder.graph_data(dataset)
    dictionary = builder.entities_document(dataset, plan)

    integrity, failures = evaluate_kg.integrity_checks(driver, plan, dictionary)
    assert failures == [], integrity
    assert integrity["unrelated_nodes"] == 1 and integrity["self_loops"] == 0

    driver.execute_query("MATCH (:Disease {name: 'a'})-[r:has_symptom]->() DELETE r")
    driver.execute_query("MATCH (d:Disease {name: 'b'}) CREATE (d)-[:accompany_with {name: 'complication', owner: $owner}]->(d)",
                         parameters_={"owner": builder.OWNER})
    _, failures = evaluate_kg.integrity_checks(driver, plan, dictionary)
    assert {"missing_relationships", "extra_relationships", "self_loops"} <= set(failures)


def test_every_template_runs_on_the_real_graph(driver, tmp_path):
    import_csv(driver, write_csv(tmp_path, "a.csv", [
        row(0, "asthma", symptoms="['wheeze', 'cough']", accompany="['rhinitis']", cure_way="['inhaler']"),
        row(1, "rhinitis", symptoms="['sneezing']"),
    ]))
    searcher = AnswerSearcher(driver=driver)
    entity = {"symptom_disease": "wheeze"}
    for question_type in TEMPLATES:
        sqls = [{"question_type": question_type, "sql": QuestionParser.sql_transfer(question_type, [entity.get(question_type, "asthma")])}]
        assert searcher.search_main(sqls), question_type
    [accompany] = searcher.search_main([{"question_type": "disease_accompany", "sql": QuestionParser.sql_transfer("disease_accompany", ["rhinitis"])}])
    assert accompany == "Accompanying conditions recorded for rhinitis: asthma"


def test_update_replaces_removed_facts_and_retires_diseases(driver, tmp_path):
    import_csv(driver, write_csv(tmp_path, "a.csv", [
        row(0, "a", description="old", symptoms="['cough', 'fever']", cure_way="['rest']"),
        row(1, "b"),
    ]))
    import_csv(driver, write_csv(tmp_path, "a2.csv", [
        row(0, "a", description="new", symptoms="['cough']", cure_way="['broken]"),
    ]))
    assert scalar(driver, "MATCH (d:Disease {name: 'a'}) RETURN d.description") == "new"
    assert scalar(driver, "MATCH (d:Disease {name: 'a'}) RETURN d.cure_way IS NULL") is True
    assert scalar(driver, "MATCH (:Disease {name: 'a'})-[:has_symptom]->(s) RETURN collect(s.name)") == ["cough"]
    assert scalar(driver, "MATCH (d:Disease {name: 'b'}) RETURN count(d)") == 0


def test_foreign_data_is_refused_and_left_untouched(driver, tmp_path):
    driver.execute_query("CREATE (:Disease {name: 'a', description: 'foreign'})")
    dataset = builder.load_dataset(write_csv(tmp_path, "a.csv", [row(0, "a")]))
    data = builder.graph_data(dataset)
    assert builder.existing_conflicts(driver, dataset, data) == [("a", "Disease node not created by this importer")]
    assert scalar(driver, "MATCH (d:Disease {name: 'a'}) RETURN d.description") == "foreign"

    driver.execute_query("MATCH (n) DETACH DELETE n")
    import_csv(driver, write_csv(tmp_path, "b.csv", [row(0, "b")]))
    driver.execute_query("MATCH (d:Disease {name: 'b'}) CREATE (:Note {text: 'keep'})-[:ABOUT]->(d)")
    dataset = builder.load_dataset(write_csv(tmp_path, "b2.csv", [row(0, "b", description="changed")]))
    data = builder.graph_data(dataset)
    assert builder.existing_conflicts(driver, dataset, data) == [("b", "relationship not created by this importer")]
    assert scalar(driver, "MATCH (:Note {text: 'keep'})-[:ABOUT]->(d:Disease {name: 'b'}) RETURN d.description") == "d"


def test_failed_write_rolls_back_to_the_previous_snapshot(driver, tmp_path, monkeypatch):
    import_csv(driver, write_csv(tmp_path, "a.csv", [row(0, "a", description="kept")]))
    before = counts(driver)
    broken = dict(builder.RELATIONSHIP_QUERIES, belongs_to="THIS IS NOT CYPHER")
    monkeypatch.setattr(builder, "RELATIONSHIP_QUERIES", broken)
    dataset = builder.load_dataset(write_csv(tmp_path, "a2.csv", [row(0, "a", description="changed"), row(1, "c")]))
    with pytest.raises(ClientError), driver.session(database=database.database_name()) as session:
        session.execute_write(builder.write_graph, builder.graph_data(dataset))
    assert counts(driver) == before
    assert scalar(driver, "MATCH (d:Disease {name: 'a'}) RETURN d.description") == "kept"


def test_query_timeout_is_enforced(driver):
    searcher = AnswerSearcher(driver=driver)
    searcher.query_timeout = 0.2
    slow = "UNWIND range(1, 1000000000) AS x WITH x WHERE x < 0 RETURN x AS subject, x AS value"
    with pytest.raises(ClientError) as raised:
        searcher.search_main([{"question_type": "disease_cause", "sql": [(slow, {})]}])
    assert "TransactionTimedOut" in raised.value.code


def test_listed_intents_match_what_the_live_graph_answers(driver, tmp_path):
    path = write_csv(tmp_path, "a.csv", [
        row(0, "a", accompany="['b']", cure_way="['rest']"),
        row(1, "b", symptoms="[]", cure_way="[]"),
    ])
    import_csv(driver, path)
    dataset = builder.load_dataset(path)
    dictionary = builder.entities_document(dataset, builder.graph_data(dataset))
    searcher = AnswerSearcher(driver=driver)
    assert dictionary["intents"]["b"] == ["disease_cause", "disease_prevention", "disease_accompany", "disease_description"]
    assert evaluate_kg.chip_consistency(searcher, dictionary) == {"diseases": 2, "mismatches": 0}

    # A listed intent the graph cannot answer is caught.
    driver.execute_query("MATCH (:Disease {name: 'a'})-[r:has_symptom]->() DELETE r")
    assert evaluate_kg.chip_consistency(searcher, dictionary)["mismatches"] == 1


def test_readiness_matches_the_imported_dictionary_only(driver, tmp_path):
    """D-022 on a real server: ready after an import; not ready when empty, resized or from another CSV."""
    path = write_csv(tmp_path, "a.csv", [row(0, "a"), row(1, "b")])
    searcher = AnswerSearcher(driver=driver)
    dataset = builder.load_dataset(path)
    expected = (len(dataset["diseases"]), dataset["source_sha256"])

    assert searcher.readiness(builder.OWNER, expected[1]) == (0, 0)  # empty database
    import_csv(driver, path)
    assert searcher.readiness(builder.OWNER, expected[1]) == (expected[0], expected[0])
    # Foreign, unmarked diseases are not counted.
    driver.execute_query("CREATE (:Disease {name: 'foreign'})")
    assert searcher.readiness(builder.OWNER, expected[1]) == (expected[0], expected[0])
    # A dictionary from another CSV does not match.
    assert searcher.readiness(builder.OWNER, "f" * 64) == (expected[0], 0)
    # A disease that lost its hash is counted but does not match.
    driver.execute_query("MATCH (d:Disease {name: 'a', owner: $owner}) REMOVE d.source_sha256", parameters_={"owner": builder.OWNER})
    assert searcher.readiness(builder.OWNER, expected[1]) == (expected[0], expected[0] - 1)


def test_a_failed_publication_is_repaired_by_rerunning_and_restarting(driver, tmp_path, monkeypatch):
    """D35 on a real server: after a commit whose dictionary was not published, a running API stays not ready even
    once a re-run publishes the file; only a restarted API (a fresh read) is ready."""
    import chatbot_graph_logic as cg
    target = tmp_path / "entities.json"
    monkeypatch.setattr(builder, "ENTITIES_PATH", target)
    monkeypatch.setattr(builder.stage_entities, "__defaults__", (target,))
    monkeypatch.setattr(builder.publish_entities, "__defaults__", (target,))
    load = builder.load_dataset
    old = write_csv(tmp_path, "old.csv", [row(0, "a"), row(1, "b")])
    new = write_csv(tmp_path, "new.csv", [row(0, "a"), row(1, "b"), row(2, "c")])
    searcher = AnswerSearcher(driver=driver)

    def ready(source):
        return searcher.readiness(builder.OWNER, source["sha256"]) == (source["diseases"], source["diseases"])

    monkeypatch.setattr(builder, "load_dataset", lambda *args: load(old))
    assert builder.main() == 0
    running = cg.ChatBotGraph.load_source(target)
    assert ready(running)

    real_replace = builder.os.replace
    monkeypatch.setattr(builder, "load_dataset", lambda *args: load(new))
    monkeypatch.setattr(builder.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("disk full")))
    assert builder.main() == 1                       # the new graph is committed, the file is not
    assert not ready(running)                        # detected: the running API's dictionary no longer matches

    monkeypatch.setattr(builder.os, "replace", real_replace)
    assert builder.main() == 0                       # the re-run publishes the file
    assert not ready(running)                        # but the running API still holds the old dictionary
    assert ready(cg.ChatBotGraph.load_source(target))  # a restart (a fresh read) is ready
