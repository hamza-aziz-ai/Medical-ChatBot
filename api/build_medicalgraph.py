import ast
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from neo4j import RoutingControl, unit_of_work

import database
from terms import clean_terms

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "medical.csv"
ENTITIES_PATH = BASE_DIR / "dictionary" / "entities.json"

SCALAR_FIELDS = {"Description": "description", "Prevention": "prevention", "Causes": "causes"}
LIST_FIELDS = {"Symptoms": "symptoms", "Accompany": "accompany", "Cure Department": "cure_department", "Cure Way": "cure_way"}

# Every node and relationship this importer writes carries this marker. A re-import replaces
# exactly the marked snapshot and never touches anything else in the database.
OWNER = "medical-chatbot-importer"
WRITE_TIMEOUT_SECONDS = 120

CONSTRAINTS = [
    "CREATE CONSTRAINT disease_name IF NOT EXISTS FOR (n:Disease) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT symptom_name IF NOT EXISTS FOR (n:Symptom) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT department_name IF NOT EXISTS FOR (n:Department) REQUIRE n.name IS UNIQUE",
]

# Unmarked nodes whose name the import would need: writing over them would overwrite foreign data.
COLLISION_QUERY = (
    "UNWIND $names AS name MATCH (n:{label} {{name: name}}) "
    "WHERE n.owner IS NULL OR n.owner <> $owner RETURN n.name AS name"
)
# Unmarked relationships attached to owned nodes: replacing the snapshot would delete them.
FOREIGN_RELATIONSHIP_QUERY = (
    "MATCH (n {owner: $owner})-[r]-() WHERE r.owner IS NULL OR r.owner <> $owner "
    "RETURN DISTINCT n.name AS name LIMIT 100"
)

RELATIONSHIP_QUERIES = {
    "has_symptom": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0], owner: $owner}) MATCH (b:Symptom {name: p[1], owner: $owner}) "
        "CREATE (a)-[:has_symptom {name: 'symptom', owner: $owner}]->(b)"
    ),
    "accompany_with": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0], owner: $owner}) MATCH (b:Disease {name: p[1], owner: $owner}) "
        "CREATE (a)-[:accompany_with {name: 'complication', owner: $owner}]->(b)"
    ),
    "disease_belongs_to": (
        "UNWIND $pairs AS p MATCH (a:Disease {name: p[0], owner: $owner}) MATCH (b:Department {name: p[1], owner: $owner}) "
        "CREATE (a)-[:disease_belongs_to {name: 'department', owner: $owner}]->(b)"
    ),
    "belongs_to": (
        "UNWIND $pairs AS p MATCH (a:Department {name: p[0], owner: $owner}) MATCH (b:Department {name: p[1], owner: $owner}) "
        "CREATE (a)-[:belongs_to {name: 'belong', owner: $owner}]->(b)"
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
            fields = sorted({key for other in group[1:] for key in content(first) if key != "excluded" and content(other)[key] != content(first)[key]})
            quarantined[name] = {"rows": [r for record in group for r in record["rows"]], "fields": fields}

    field_issues = [issue for issue in issues if records[issue[0] - 1]["name"] in diseases]
    return {
        "source_file": Path(path).name,
        # Hash with normalized line endings so Windows and Linux checkouts agree.
        "source_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
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


def existing_conflicts(driver, dataset, data):
    def names(query, parameters):
        records, _, _ = driver.execute_query(
            query, parameters_={"owner": OWNER, **parameters},
            database_=database.database_name(), routing_=RoutingControl.READ,
        )
        return [record["name"] for record in records]

    planned = {
        "Disease": sorted({row["name"] for row in data["diseases"]} | set(dataset["quarantined_names"])),
        "Symptom": data["symptoms"],
        "Department": data["departments"],
    }
    conflicts = []
    for label, candidates in planned.items():
        if candidates:
            found = names(COLLISION_QUERY.format(label=label), {"names": candidates})
            conflicts += [(name, f"{label} node not created by this importer") for name in found]
    conflicts += [(name, "relationship not created by this importer") for name in names(FOREIGN_RELATIONSHIP_QUERY, {})]
    return conflicts


def create_constraints(driver):
    for query in CONSTRAINTS:
        driver.execute_query(query, database_=database.database_name())


@unit_of_work(timeout=WRITE_TIMEOUT_SECONDS)
def write_graph(tx, data):
    # Replace the importer's own snapshot; guards have already confirmed nothing foreign is attached.
    tx.run("MATCH (n {owner: $owner}) DETACH DELETE n", owner=OWNER).consume()
    tx.run(
        "UNWIND $rows AS row CREATE (d:Disease) SET d = row.properties, d.name = row.name, d.owner = $owner",
        rows=data["diseases"], owner=OWNER,
    ).consume()
    tx.run("UNWIND $names AS name CREATE (:Symptom {name: name, owner: $owner})", names=data["symptoms"], owner=OWNER).consume()
    tx.run("UNWIND $names AS name CREATE (:Department {name: name, owner: $owner})", names=data["departments"], owner=OWNER).consume()
    for relationship, query in RELATIONSHIP_QUERIES.items():
        tx.run(query, pairs=[list(pair) for pair in data["edges"][relationship]], owner=OWNER).consume()


def entities_document(dataset, data):
    return {
        "source_sha256": dataset["source_sha256"],
        "diseases": sorted(row["name"] for row in data["diseases"]),
        "departments": data["departments"],
        "symptoms": data["symptoms"],
    }


def stage_entities(document, path=ENTITIES_PATH):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as file:
        json.dump(document, file, ensure_ascii=False, indent=1)
        file.write("\n")
    return Path(file.name)


def publish_entities(staged, path=ENTITIES_PATH):
    os.replace(staged, path)


def discard(staged):
    try:
        staged.unlink()
    except FileNotFoundError:
        pass


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
        staged = stage_entities(entities_document(dataset, data))
    except OSError as error:
        print(f"Could not stage the entity dictionary ({type(error).__name__}); nothing was changed.", file=sys.stderr)
        return 1

    try:
        with database.create_driver() as driver:
            conflicts = existing_conflicts(driver, dataset, data)
            if conflicts:
                for name, reason in conflicts:
                    print(f"Refusing import: '{name}' has a {reason}", file=sys.stderr)
                print("Reconcile these records manually or import into a fresh database. Nothing was changed.", file=sys.stderr)
                discard(staged)
                return 1
            create_constraints(driver)
            with driver.session(database=database.database_name()) as session:
                session.execute_write(write_graph, data)
    except Exception as error:
        discard(staged)
        print(f"Import failed ({type(error).__name__}); no graph data was committed.", file=sys.stderr)
        return 1

    try:
        publish_entities(staged)
    except OSError as error:
        discard(staged)
        print(
            f"The graph was committed, but publishing the entity dictionary failed ({type(error).__name__}). "
            "The previous dictionary is unchanged; re-run the import to publish it.",
            file=sys.stderr,
        )
        return 1

    print("Import committed and entity dictionary published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
