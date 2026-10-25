import ast
import csv
import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

from neo4j import RoutingControl

import database
from terms import clean_terms

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "medical.csv"
DICTIONARY_DIR = BASE_DIR / "dictionary"

SCALAR_FIELDS = {"Description": "description", "Prevention": "prevention", "Causes": "causes"}
LIST_FIELDS = {"Symptoms": "symptoms", "Accompany": "accompany", "Cure Department": "cure_department", "Cure Way": "cure_way"}

# Graph data each list field produces. A quarantined field must not already have data here,
# because MERGE and SET += never remove what an earlier import wrote.
STALE_FIELD_QUERIES = {
    "symptoms": "UNWIND $names AS name MATCH (d:Disease {name: name})-[:has_symptom]->() RETURN DISTINCT d.name AS name",
    "accompany": "UNWIND $names AS name MATCH (d:Disease {name: name})-[:accompany_with]->() RETURN DISTINCT d.name AS name",
    "cure_department": (
        "UNWIND $names AS name MATCH (d:Disease {name: name}) "
        "WHERE d.cure_department IS NOT NULL OR (d)-[:disease_belongs_to]->() RETURN DISTINCT d.name AS name"
    ),
    "cure_way": "UNWIND $names AS name MATCH (d:Disease {name: name}) WHERE d.cure_way IS NOT NULL RETURN DISTINCT d.name AS name",
}

CONSTRAINTS = [
    "CREATE CONSTRAINT disease_name IF NOT EXISTS FOR (n:Disease) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT symptom_name IF NOT EXISTS FOR (n:Symptom) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT department_name IF NOT EXISTS FOR (n:Department) REQUIRE n.name IS UNIQUE",
]

RELATIONSHIP_QUERIES = {
    "has_symptom": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0]}) MATCH (b:Symptom {name: p[1]}) "
        "MERGE (a)-[:has_symptom {name: 'symptom'}]->(b)"
    ),
    "accompany_with": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0]}) MATCH (b:Disease {name: p[1]}) "
        "MERGE (a)-[:accompany_with {name: 'complication'}]->(b)"
    ),
    "disease_belongs_to": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0]}) MATCH (b:Department {name: p[1]}) "
        "MERGE (a)-[:disease_belongs_to {name: 'department'}]->(b)"
    ),
    "belongs_to": (
        "UNWIND $pairs AS p MATCH (a:Department {name: p[0]}) MATCH (b:Department {name: p[1]}) "
        "MERGE (a)-[:belongs_to {name: 'belong'}]->(b)"
    ),
}


def parse_list(text):
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return clean_terms(value)
    return None


def parse_record(row, row_number, issues):
    record = {"name": row["Name"].strip(), "rows": [row_number], "excluded": set()}
    for column, key in SCALAR_FIELDS.items():
        record[key] = row[column].strip()
    for column, key in LIST_FIELDS.items():
        values = parse_list(row[column])
        if values is None:
            record["excluded"].add(key)
            issues.append((row_number, column, "not a valid list of strings"))
        record[key] = values
    return record


def content(record):
    return {key: value for key, value in record.items() if key != "rows"}


def load_dataset(path=CSV_PATH):
    raw = Path(path).read_bytes()
    issues = []
    records = [
        parse_record(row, row_number, issues)
        for row_number, row in enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")), start=1)
    ]

    by_name = {}
    for record in records:
        by_name.setdefault(record["name"], []).append(record)

    diseases, quarantined = {}, {}
    for name, group in by_name.items():
        first = group[0]
        if all(content(other) == content(first) for other in group[1:]):
            first["rows"] = [row for record in group for row in record["rows"]]
            diseases[name] = first
        else:
            fields = sorted({key for other in group[1:] for key in content(first) if content(other)[key] != content(first)[key]})
            quarantined[name] = {"rows": [r for record in group for r in record["rows"]], "fields": fields}

    field_issues = [issue for issue in issues if records[issue[0] - 1]["name"] in diseases]
    return {
        "source_file": Path(path).name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "diseases": diseases,
        "quarantined_names": quarantined,
        "field_issues": field_issues,
    }


def graph_data(dataset):
    diseases = dataset["diseases"]
    disease_rows, symptoms, departments = [], set(), set()
    edges = {name: set() for name in RELATIONSHIP_QUERIES}
    unresolved = []

    for name, record in diseases.items():
        properties = {key: record[key] for key in SCALAR_FIELDS.values() if record[key]}
        for key in ("cure_department", "cure_way"):
            if record[key] is not None:
                properties[key] = record[key]
        properties.update(
            source_file=dataset["source_file"],
            source_sha256=dataset["source_sha256"],
            source_rows=record["rows"],
            clinical_review="unverified",
        )
        disease_rows.append({"name": name, "properties": properties})

        for symptom in record["symptoms"] or []:
            symptoms.add(symptom)
            edges["has_symptom"].add((name, symptom))

        for companion in record["accompany"] or []:
            if companion in diseases:
                edges["accompany_with"].add((name, companion))
            else:
                unresolved.append((name, companion))

        cure_department = record["cure_department"] or []
        departments.update(cure_department)
        if len(cure_department) == 1:
            edges["disease_belongs_to"].add((name, cure_department[0]))
        elif len(cure_department) == 2:
            parent, child = cure_department
            edges["belongs_to"].add((child, parent))
            edges["disease_belongs_to"].add((name, child))

    return {
        "diseases": disease_rows,
        "symptoms": sorted(symptoms),
        "departments": sorted(departments),
        "edges": {name: sorted(pairs) for name, pairs in edges.items()},
        "unresolved": unresolved,
    }


def existing_conflicts(driver, dataset):
    def names(query, candidates):
        if not candidates:
            return []
        records, _, _ = driver.execute_query(
            query, parameters_={"names": sorted(candidates)},
            database_=database.database_name(), routing_=RoutingControl.READ,
        )
        return [record["name"] for record in records]

    conflicts = [
        (name, "conflicting duplicate name")
        for name in names("UNWIND $names AS name MATCH (d:Disease {name: name}) RETURN d.name AS name", dataset["quarantined_names"])
    ]
    for field, query in STALE_FIELD_QUERIES.items():
        excluded = [name for name, record in dataset["diseases"].items() if field in record["excluded"]]
        conflicts += [(name, f"quarantined field {field}") for name in names(query, excluded)]
    return conflicts


def create_constraints(driver):
    for query in CONSTRAINTS:
        driver.execute_query(query, database_=database.database_name())


def write_graph(tx, data):
    tx.run("UNWIND $rows AS row MERGE (d:Disease {name: row.name}) SET d += row.properties", rows=data["diseases"]).consume()
    tx.run("UNWIND $names AS name MERGE (:Symptom {name: name})", names=data["symptoms"]).consume()
    tx.run("UNWIND $names AS name MERGE (:Department {name: name})", names=data["departments"]).consume()
    for relationship, query in RELATIONSHIP_QUERIES.items():
        tx.run(query, pairs=[list(pair) for pair in data["edges"][relationship]]).consume()


def write_lines_atomically(path, lines):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as file:
        file.write("\n".join(lines))
    os.replace(file.name, path)


def export_dictionaries(data):
    write_lines_atomically(DICTIONARY_DIR / "diseases.txt", sorted(row["name"] for row in data["diseases"]))
    write_lines_atomically(DICTIONARY_DIR / "symptoms.txt", data["symptoms"])
    write_lines_atomically(DICTIONARY_DIR / "departments.txt", data["departments"])


def print_report(dataset, data):
    for name, info in sorted(dataset["quarantined_names"].items()):
        print(f"Excluded disease '{name}' (rows {info['rows']}): conflicting fields {', '.join(info['fields'])}")
    for row, column, reason in dataset["field_issues"]:
        print(f"Excluded field: row {row}, column '{column}': {reason}")
    print(f"Accompanying links with no matching disease: {len(data['unresolved'])}")
    print(
        f"Diseases: {len(data['diseases'])} imported, {len(dataset['quarantined_names'])} names excluded; "
        f"fields excluded: {len(dataset['field_issues'])}; symptoms: {len(data['symptoms'])}; "
        f"departments: {len(data['departments'])}"
    )


def main():
    dataset = load_dataset()
    data = graph_data(dataset)
    print_report(dataset, data)

    try:
        with database.create_driver() as driver:
            conflicts = existing_conflicts(driver, dataset)
            if conflicts:
                for name, reason in conflicts:
                    print(f"Refusing import: '{name}' already has graph data for a {reason}", file=sys.stderr)
                print("Reconcile these records manually or import into a fresh database. Nothing was changed.", file=sys.stderr)
                return 1
            create_constraints(driver)
            with driver.session(database=database.database_name()) as session:
                session.execute_write(write_graph, data)
    except Exception as error:
        print(f"Import failed ({type(error).__name__}); no graph data was committed.", file=sys.stderr)
        return 1

    try:
        export_dictionaries(data)
    except OSError as error:
        print(f"The graph was committed, but exporting the dictionaries failed ({type(error).__name__}).", file=sys.stderr)
        return 1

    print("Import committed and dictionaries exported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
