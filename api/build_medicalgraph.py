import ast
import csv
import hashlib
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from neo4j import RoutingControl, unit_of_work
from neo4j.exceptions import IncompleteCommit

import app_logging
import database
from terms import clean_terms, is_valid_term

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "medical.csv"
ENTITIES_PATH = BASE_DIR / "dictionary" / "entities.json"

SCALAR_FIELDS = {"Description": "description", "Prevention": "prevention", "Causes": "causes"}
LIST_FIELDS = {"Symptoms": "symptoms", "Accompany": "accompany", "Cure Department": "cure_department", "Cure Way": "cure_way"}
REQUIRED_COLUMNS = {"Name", *SCALAR_FIELDS, *LIST_FIELDS}

# Every node and relationship this importer writes carries this marker. A re-import replaces
# exactly the marked snapshot and never touches anything else in the database.
OWNER = "medical-chatbot-importer"

# D35: a graph commit and the dictionary file cannot be published as one unit, and a running API keeps the
# dictionary it read at start, so every partial outcome is repaired the same way.
RECOVER = ("Fix the publication error, rerun the same import, then restart the API and verify readiness "
           "(GET /health) before serving.")
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

# Named so the plan fingerprint (D-023) covers how the graph is written, not only what is written.
NODE_QUERIES = {
    "delete": "MATCH (n {owner: $owner}) DETACH DELETE n",
    "diseases": "UNWIND $rows AS row CREATE (d:Disease) SET d = row.properties, d.name = row.name, d.owner = $owner",
    "symptoms": "UNWIND $names AS name CREATE (:Symptom {name: name, owner: $owner})",
    "departments": "UNWIND $names AS name CREATE (:Department {name: name, owner: $owner})",
}

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
        elif key == "cure_department" and len(set(values)) > 2:
            # Only a department or a [parent, child] pair can be linked; guessing the hierarchy would invent facts.
            values = None
            record["excluded"].add(key)
            issues.append((row_number, column, "more than two departments"))
        record[key] = values
    return record


def content(record):
    return {key: value for key, value in record.items() if key != "rows"}


def load_dataset(path=CSV_PATH):
    raw = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"{Path(path).name} is missing columns: {', '.join(sorted(missing))}")
    issues = []
    records = [parse_record(row, row_number, issues) for row_number, row in enumerate(reader, start=1)]
    blank = [record["rows"][0] for record in records if not record["name"]]
    if blank:
        raise ValueError(f"{Path(path).name} has rows without a disease name: {blank[:10]}")

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

    if not diseases:
        raise ValueError(f"{Path(path).name} has no diseases left after quarantine")
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
    unresolved, self_companions, repeated_departments = [], [], []

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
            if companion == name:
                # A disease listed as its own complication carries no information.
                self_companions.append(name)
            elif companion in diseases:
                edges["accompany_with"].add((name, companion))
            else:
                unresolved.append((name, companion))

        # ['oncology', 'oncology'] names one department, not a department that is its own parent.
        cure_department = list(dict.fromkeys(record["cure_department"] or []))
        if len(cure_department) < len(record["cure_department"] or []):
            repeated_departments.append(name)
        departments.update(cure_department)
        if len(cure_department) == 1:
            edges["disease_belongs_to"].add((name, cure_department[0]))
        elif len(cure_department) == 2:
            parent, child = cure_department
            edges["belongs_to"].add((child, parent))
            edges["disease_belongs_to"].add((name, child))

    cycle = department_cycle(edges["belongs_to"])
    if cycle:
        raise ValueError(f"department hierarchy has a cycle: {' -> '.join(cycle)}")

    return {
        "diseases": disease_rows,
        "symptoms": sorted(symptoms),
        "departments": sorted(departments),
        "edges": {name: sorted(pairs) for name, pairs in edges.items()},
        "unresolved": unresolved,
        "self_companions": sorted(self_companions),
        "repeated_departments": sorted(repeated_departments),
    }


def department_cycle(child_parent_pairs):
    """Return one cycle in the child -> parent hierarchy as a list of names, or None."""
    parents = {}
    for child, parent in child_parent_pairs:
        parents.setdefault(child, set()).add(parent)
    done = set()

    def visit(node, path):
        if node in path:
            return path[path.index(node):] + [node]
        if node in done:
            return None
        for parent in sorted(parents.get(node, ())):
            found = visit(parent, path + [node])
            if found:
                return found
        done.add(node)
        return None

    for start in sorted(parents):
        found = visit(start, [])
        if found:
            return found
    return None


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
    tx.run(NODE_QUERIES["delete"], owner=OWNER).consume()
    tx.run(NODE_QUERIES["diseases"], rows=data["diseases"], owner=OWNER).consume()
    tx.run(NODE_QUERIES["symptoms"], names=data["symptoms"], owner=OWNER).consume()
    tx.run(NODE_QUERIES["departments"], names=data["departments"], owner=OWNER).consume()
    for relationship, query in RELATIONSHIP_QUERIES.items():
        tx.run(query, pairs=[list(pair) for pair in data["edges"][relationship]], owner=OWNER).consume()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def plan(dataset):
    """The graph data and the dictionary for one import, both stamped with the same plan_sha256 (D-023).

    The fingerprint covers the intended graph (unordered collections sorted, list order inside properties kept),
    the dictionary and the write queries, so the API can tell whether the graph it reads is the one its dictionary
    was published with. It is computed before the stamps are added, so it never hashes itself.
    """
    data = graph_data(dataset)
    document = entities_document(dataset, data)
    content = {
        "graph": {
            "diseases": sorted(({"name": row["name"], "properties": row["properties"]} for row in data["diseases"]),
                               key=lambda row: row["name"]),
            "symptoms": sorted(data["symptoms"]),
            "departments": sorted(data["departments"]),
            "edges": {kind: sorted(list(pair) for pair in pairs) for kind, pairs in sorted(data["edges"].items())},
        },
        "dictionary": document,
        "writer": {"nodes": NODE_QUERIES, "relationships": RELATIONSHIP_QUERIES},
    }
    fingerprint = hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()
    for row in data["diseases"]:
        row["properties"]["plan_sha256"] = fingerprint
    document["plan_sha256"] = fingerprint
    return data, document


def entities_document(dataset, data):
    return {
        "source_sha256": dataset["source_sha256"],
        "diseases": sorted(row["name"] for row in data["diseases"]),
        "departments": data["departments"],
        "symptoms": data["symptoms"],
        "intents": disease_intents(data),
    }


def disease_intents(data):
    """{disease: intents that have an answer}, so suggestion chips never lead to "nothing recorded".

    Written with the dictionary from the same import (D-015), so the API needs no database call to know it.
    Mirrors what the answer templates return: text properties that are set, list values that are valid terms,
    symptom links, and complication links in either direction.
    """
    with_symptoms = {disease for disease, _ in data["edges"]["has_symptom"]}
    with_companions = {disease for pair in data["edges"]["accompany_with"] for disease in pair}
    intents = {}
    for row in sorted(data["diseases"], key=lambda row: row["name"]):
        name, properties = row["name"], row["properties"]
        available = {
            "disease_symptom": name in with_symptoms,
            "disease_cause": bool(properties.get("causes")),
            "disease_prevention": bool(properties.get("prevention")),
            "disease_cure_way": any(is_valid_term(value) for value in properties.get("cure_way") or []),
            "disease_accompany": name in with_companions,
            "disease_description": bool(properties.get("description")),
        }
        intents[name] = [intent for intent, present in available.items() if present]
    return intents


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


logger = logging.getLogger("build_medicalgraph")


def report(message, level=logging.INFO):
    """Show a message on the console and record it in the importer log."""
    print(message, file=sys.stderr if level >= logging.WARNING else sys.stdout)
    logger.log(level, message)


def print_report(dataset, data):
    for name, info in sorted(dataset["quarantined_names"].items()):
        report(f"Excluded disease '{name}' (rows {info['rows']}): conflicting fields {', '.join(info['fields'])}")
    for row, column, reason in dataset["field_issues"]:
        report(f"Excluded field: row {row}, column '{column}': {reason}")
    report(f"Accompanying links with no matching disease: {len(data['unresolved'])}")
    if data["self_companions"]:
        report(f"Diseases listed as their own complication (link skipped): {', '.join(data['self_companions'])}")
    if data["repeated_departments"]:
        report(f"Diseases with a repeated department (linked once, no hierarchy edge): {len(data['repeated_departments'])}")
    report(
        f"Diseases: {len(data['diseases'])} imported, {len(dataset['quarantined_names'])} names excluded; "
        f"fields excluded: {len(dataset['field_issues'])}; symptoms: {len(data['symptoms'])}; "
        f"departments: {len(data['departments'])}"
    )


def main():
    # The pre-write checks query labels and properties that an empty database does not have yet;
    # Neo4j reports those as "does not exist" notifications, which are expected here.
    loaded = database.load_env_file()
    app_logging.setup_logging()
    database.log_env_loaded(loaded)
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
    report("Import started")
    try:
        dataset = load_dataset()
        data, document = plan(dataset)
    except ValueError as error:
        report(f"Refusing import: {error}. Nothing was changed.", logging.ERROR)
        return 1
    print_report(dataset, data)

    try:
        staged = stage_entities(document)
    except OSError as error:
        report(f"Could not stage the entity dictionary ({type(error).__name__}); nothing was changed.", logging.ERROR)
        return 1

    try:
        with database.create_driver() as driver:
            conflicts = existing_conflicts(driver, dataset, data)
            if conflicts:
                for name, reason in conflicts:
                    report(f"Refusing import: '{name}' has a {reason}", logging.WARNING)
                report("Reconcile these records manually or import into a fresh database. Nothing was changed.", logging.WARNING)
                discard(staged)
                return 1
            create_constraints(driver)
            with driver.session(database=database.database_name()) as session:
                session.execute_write(write_graph, data)
    except IncompleteCommit:
        # The commit may or may not have happened (D35), so the graph and the dictionary may now disagree.
        discard(staged)
        report("The import's commit outcome is unknown. " + RECOVER, logging.ERROR)
        return 1
    except Exception as error:
        discard(staged)
        report(f"Import failed ({type(error).__name__}); no graph data was committed.", logging.ERROR)
        return 1

    try:
        publish_entities(staged)
    except OSError as error:
        discard(staged)
        report(f"Graph committed, but dictionary publication failed ({type(error).__name__}). " + RECOVER, logging.ERROR)
        return 1

    report("Import committed and entity dictionary published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
