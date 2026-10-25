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


def test_import_refuses_when_quarantined_name_exists(tmp_path):
    path = write_csv(tmp_path, row(0, "b"), row(1, "b", description="other"))
    dataset = builder.load_dataset(path)
    driver = FakeDriver(rows=[{"name": "b"}])
    assert ("b", "conflicting duplicate name") in builder.existing_conflicts(driver, dataset)


def test_import_refuses_stale_data_for_quarantined_field(tmp_path):
    path = write_csv(tmp_path, row(0, "x", cure_way="['broken]"))
    dataset = builder.load_dataset(path)
    stale = {builder.STALE_FIELD_QUERIES["cure_way"]: [{"name": "x"}]}
    driver = FakeDriver(results=stale)
    assert builder.existing_conflicts(driver, dataset) == [("x", "quarantined field cure_way")]


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


def test_failed_write_exits_non_zero_and_skips_export(monkeypatch):
    exported = []
    monkeypatch.setattr(database, "create_driver", lambda: FailingDriver())
    monkeypatch.setattr(builder, "export_dictionaries", lambda data: exported.append(data))
    assert builder.main() == 1
    assert exported == []


def test_missing_password_is_a_named_error(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD must be set"):
        database.create_driver()
