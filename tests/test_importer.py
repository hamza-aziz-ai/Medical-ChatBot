import pytest

import build_medicalgraph as builder
import database
from conftest import FakeDriver

HEADER = "S.No.,Name,Description,Prevention,Causes,Symptoms,Accompany,Cure Department,Cure Way\n"


def write_csv(tmp_path, *rows):
    path = tmp_path / "medical.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def row(number, name, description="d", symptoms="['cough']", accompany="[]", cure_way="['rest']"):
    return f'{number},{name},{description},p,c,"{symptoms}","{accompany}","[\'internal medicine\']","{cure_way}"\n'


def test_real_dataset_quarantines_conflicts_and_artefacts():
    dataset = builder.load_dataset()
    data = builder.graph_data(dataset)
    assert len(dataset["quarantined_names"]) == 8
    assert "pneumonia" in dataset["quarantined_names"]
    assert len(data["diseases"]) == 658
    assert not {"", "...", "living"} & set(data["symptoms"])


def test_malformed_field_is_quarantined_without_guessing(tmp_path):
    path = write_csv(tmp_path, row(0, "x", symptoms="['pain, chest', 'myasthenia gravis]"))
    dataset = builder.load_dataset(path)
    record = dataset["diseases"]["x"]
    assert record["symptoms"] is None and "symptoms" in record["excluded"]
    assert record["cure_way"] == ["rest"]
    assert dataset["field_issues"] == [(1, "Symptoms", "not a valid list of strings")]
    assert builder.graph_data(dataset)["edges"]["has_symptom"] == []


def test_identical_duplicates_collapse_and_conflicts_are_excluded(tmp_path):
    path = write_csv(tmp_path, row(0, "a"), row(1, "a"), row(2, "b"), row(3, "b", description="other"))
    dataset = builder.load_dataset(path)
    assert dataset["diseases"]["a"]["rows"] == [1, 2]
    assert dataset["quarantined_names"] == {"b": {"rows": [3, 4], "fields": ["description"]}}


def test_unknown_companions_are_reported_not_created(tmp_path):
    path = write_csv(tmp_path, row(0, "a", accompany="['ghost']"))
    data = builder.graph_data(builder.load_dataset(path))
    assert data["edges"]["accompany_with"] == []
    assert data["unresolved"] == [("a", "ghost")]


def test_lineage_is_recorded(tmp_path):
    path = write_csv(tmp_path, row(0, "a"))
    [disease] = builder.graph_data(builder.load_dataset(path))["diseases"]
    assert disease["properties"]["clinical_review"] == "unverified"
    assert disease["properties"]["source_rows"] == [1]
    assert len(disease["properties"]["source_sha256"]) == 64


@pytest.mark.parametrize("text, problem", [
    ("S.No.,Name,Description\n0,a,d\n", "missing columns: Accompany, Causes, Cure Department, Cure Way, Prevention, Symptoms"),
    (HEADER + row(0, "a") + row(1, " "), "rows without a disease name: [2]"),
    (HEADER + row(0, "a") + row(1, "a", description="other"), "no diseases left after quarantine"),
])
def test_invalid_datasets_are_refused(tmp_path, text, problem):
    path = tmp_path / "medical.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=problem.replace("[", r"\[").replace("]", r"\]")):
        builder.load_dataset(path)


def department_row(number, name, departments, accompany="[]"):
    return f'{number},{name},d,p,c,"[\'cough\']","{accompany}","{departments}","[\'rest\']"\n'


def test_self_companion_is_skipped_and_reported(tmp_path):
    data = builder.graph_data(builder.load_dataset(write_csv(tmp_path, row(0, "a", accompany="['a', 'b']"), row(1, "b"))))
    assert data["edges"]["accompany_with"] == [("a", "b")]
    assert data["self_companions"] == ["a"]


def test_repeated_department_is_one_department_without_a_hierarchy_edge(tmp_path):
    data = builder.graph_data(builder.load_dataset(write_csv(tmp_path, department_row(0, "a", "['oncology', 'oncology']"))))
    assert data["edges"]["disease_belongs_to"] == [("a", "oncology")]
    assert data["edges"]["belongs_to"] == []
    assert data["repeated_departments"] == ["a"]
    # The source list is kept as written.
    assert data["diseases"][0]["properties"]["cure_department"] == ["oncology", "oncology"]


def test_more_than_two_departments_is_quarantined_for_that_disease(tmp_path):
    dataset = builder.load_dataset(write_csv(tmp_path, department_row(0, "a", "['x', 'y', 'z']"), department_row(1, "b", "['x', 'y']")))
    assert dataset["field_issues"] == [(1, "Cure Department", "more than two departments")]
    data = builder.graph_data(dataset)
    assert data["edges"]["disease_belongs_to"] == [("b", "y")]
    assert "cure_department" not in data["diseases"][0]["properties"]


def test_department_cycle_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    path = write_csv(tmp_path, department_row(0, "a", "['x', 'y']"), department_row(1, "b", "['y', 'x']"))
    with pytest.raises(ValueError, match="department hierarchy has a cycle"):
        builder.graph_data(builder.load_dataset(path))
    load = builder.load_dataset
    monkeypatch.setattr(builder, "load_dataset", lambda: load(path))
    monkeypatch.setattr(builder.database, "create_driver", lambda: pytest.fail("must not connect"))
    assert builder.main() == 1


def plan(path):
    dataset = builder.load_dataset(path)
    return dataset, builder.graph_data(dataset)


def test_import_refuses_foreign_node_collisions(tmp_path):
    dataset, data = plan(write_csv(tmp_path, row(0, "a"), row(1, "b"), row(2, "b", description="other")))
    disease_query = builder.COLLISION_QUERY.format(label="Disease")
    driver = FakeDriver(results={disease_query: [{"name": "b"}]})
    conflicts = builder.existing_conflicts(driver, dataset, data)
    assert conflicts == [("b", "Disease node not created by this importer")]
    planned = dict(driver.calls)[disease_query]
    assert planned["names"] == ["a", "b"] and planned["owner"] == builder.OWNER


def test_import_refuses_foreign_relationships_on_owned_nodes(tmp_path):
    dataset, data = plan(write_csv(tmp_path, row(0, "a")))
    driver = FakeDriver(results={builder.FOREIGN_RELATIONSHIP_QUERY: [{"name": "a"}]})
    assert builder.existing_conflicts(driver, dataset, data) == [("a", "relationship not created by this importer")]


class RecordingTx:
    def __init__(self):
        self.runs = []

    def run(self, query, **params):
        self.runs.append((query, params))
        return self

    def consume(self):
        pass


def test_write_replaces_only_the_owned_snapshot(tmp_path):
    _, data = plan(write_csv(tmp_path, row(0, "a")))
    tx = RecordingTx()
    builder.write_graph(tx, data)
    first_query, first_params = tx.runs[0]
    assert first_query == "MATCH (n {owner: $owner}) DETACH DELETE n"
    assert all(params.get("owner") == builder.OWNER for _, params in tx.runs)
    assert all("{owner: $owner}" in q or "owner: $owner" in q or "d.owner = $owner" in q for q, _ in tx.runs)
    assert builder.write_graph.timeout == builder.WRITE_TIMEOUT_SECONDS


class FailingSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, *args):
        raise RuntimeError("write failed")


class FailingDriver(FakeDriver):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def session(self, **kwargs):
        return FailingSession()


def test_failed_write_keeps_the_previous_dictionary(monkeypatch, tmp_path):
    target = tmp_path / "entities.json"
    target.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(builder, "ENTITIES_PATH", target)
    monkeypatch.setattr(builder.stage_entities, "__defaults__", (target,))
    monkeypatch.setattr(builder.publish_entities, "__defaults__", (target,))
    monkeypatch.setattr(database, "create_driver", lambda: FailingDriver())
    assert builder.main() == 1
    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_publication_keeps_the_previous_dictionary(monkeypatch, tmp_path):
    target = tmp_path / "entities.json"
    target.write_text("previous", encoding="utf-8")
    staged = builder.stage_entities({"diseases": []}, target)

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(builder.os, "replace", broken_replace)
    with pytest.raises(OSError):
        builder.publish_entities(staged, target)
    builder.discard(staged)
    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob("*.tmp")) == []


def test_committed_dictionary_matches_the_import_plan():
    import json

    dataset = builder.load_dataset()
    _, expected = builder.plan(dataset)
    committed = json.loads(builder.ENTITIES_PATH.read_text(encoding="utf-8"))
    assert committed == expected


def test_missing_password_is_a_named_error(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD must be set"):
        database.create_driver()


# D35: partial outcomes name the full recovery: fix, re-run, restart the API, check /health.

class CommittingSession(FailingSession):
    def __init__(self, error=None):
        self.error = error

    def execute_write(self, *args):
        if self.error:
            raise self.error


def run_importer(monkeypatch, tmp_path, session):
    target = tmp_path / "entities.json"
    target.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(builder, "ENTITIES_PATH", target)
    monkeypatch.setattr(builder.stage_entities, "__defaults__", (target,))
    monkeypatch.setattr(builder.publish_entities, "__defaults__", (target,))
    driver = FailingDriver()
    driver.session = lambda **kwargs: session
    monkeypatch.setattr(database, "create_driver", lambda: driver)
    return builder.main(), target


def test_an_unknown_commit_outcome_says_how_to_recover(monkeypatch, tmp_path, capsys):
    from neo4j.exceptions import IncompleteCommit
    code, target = run_importer(monkeypatch, tmp_path, CommittingSession(IncompleteCommit("lost")))
    err = capsys.readouterr().err
    assert code == 1 and "commit outcome is unknown" in err and "restart the API" in err and "/health" in err
    assert "no graph data was committed" not in err
    assert target.read_text(encoding="utf-8") == "previous"


def test_a_failed_publication_after_the_commit_says_how_to_recover(monkeypatch, tmp_path, capsys):
    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(builder.os, "replace", broken_replace)
    code, target = run_importer(monkeypatch, tmp_path, CommittingSession())
    err = capsys.readouterr().err
    assert code == 1 and "Graph committed, but dictionary publication failed" in err and "restart the API" in err
    assert target.read_text(encoding="utf-8") == "previous" and list(tmp_path.glob("*.tmp")) == []


# D-023: the plan fingerprint.

def test_the_plan_fingerprint_is_stamped_on_every_disease_and_the_dictionary():
    data, document = builder.plan(builder.load_dataset())
    stamps = {row["properties"]["plan_sha256"] for row in data["diseases"]}
    assert stamps == {document["plan_sha256"]} and len(document["plan_sha256"]) == 64


def test_the_fingerprint_ignores_order_but_not_content(monkeypatch):
    dataset = builder.load_dataset()
    base = builder.plan(dataset)[1]["plan_sha256"]
    # Same content, different collection and key order: same fingerprint.
    reordered = dict(reversed(list(dataset.items())))
    reordered["diseases"] = dict(reversed(list(dataset["diseases"].items())))
    assert builder.plan(reordered)[1]["plan_sha256"] == base

    def changed(mutate):
        copy = {**dataset, "diseases": {name: dict(record) for name, record in dataset["diseases"].items()}}
        mutate(copy)
        return builder.plan(copy)

    # Only a description changes: the dictionary (names, intents) is the same, the fingerprint is not.
    name = next(n for n, r in dataset["diseases"].items() if r["description"])
    data, document = changed(lambda d: d["diseases"][name].update(description=d["diseases"][name]["description"] + " (edited)"))
    plain = {k: v for k, v in document.items() if k != "plan_sha256"}
    original = {k: v for k, v in builder.plan(dataset)[1].items() if k != "plan_sha256"}
    assert plain == original and document["plan_sha256"] != base

    # Only how a relationship is written changes: the fingerprint changes too.
    queries = dict(builder.RELATIONSHIP_QUERIES)
    queries["has_symptom"] = queries["has_symptom"].replace("(a)-[:has_symptom", "(b)<-[:has_symptom")
    monkeypatch.setattr(builder, "RELATIONSHIP_QUERIES", queries)
    assert builder.plan(dataset)[1]["plan_sha256"] != base
