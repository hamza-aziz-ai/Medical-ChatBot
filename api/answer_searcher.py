import hashlib
import json
import logging
from pathlib import Path

from neo4j import READ_ACCESS, Query, RoutingControl

import database
import text_format
from terms import is_valid_term

logger = logging.getLogger(__name__)

# D-022, D-023: how many importer-owned diseases exist, and how many carry the plan fingerprint of the dictionary
# the API loaded. count(CASE ...) rather than collect(DISTINCT ...), because collect skips diseases with no stamp.
READINESS_QUERY = ("MATCH (d:Disease {owner: $owner}) RETURN count(d) AS diseases, "
                   "count(CASE WHEN d.plan_sha256 = $plan THEN 1 END) AS matching")
READINESS_TIMEOUT = 1.0

# D-029: approved rewordings of the three prose answers, matched on their exact input and output and on the formatter's
# identity; anything else shows the original. Generated and approved offline only (scripts/reword_answers.py).
REWORDINGS_PATH = Path(__file__).resolve().parent / "dictionary" / "rewordings.json"
PROSE_INTENTS = ("disease_description", "disease_cause", "disease_prevention")


def canonical_input(subject, intent, values):
    """The exact input a rewording was made from: the values as group_values() serves them, in order."""
    return json.dumps({"intent": intent, "subject": subject, "values": list(values)}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sections_digest(sections):
    return digest(json.dumps(sections, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def valid_sections(sections):
    def text_or_none(value):
        return value is None or (isinstance(value, str) and value.strip() != "")

    return isinstance(sections, list) and bool(sections) and all(
        isinstance(s, dict) and set(s) == {"heading", "paragraph", "items"} and text_or_none(s["heading"])
        and text_or_none(s["paragraph"]) and isinstance(s["items"], list) and all(isinstance(i, str) and i.strip() for i in s["items"])
        and (s["paragraph"] or s["items"]) for s in sections)


def load_rewordings(path=REWORDINGS_PATH):
    """{(subject, intent): entry} for approved, well-formed entries made with this formatter; bad ones are skipped
    and counted, never served. A missing or unreadable file means no rewordings."""
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError, AttributeError) as error:
        logger.warning("No rewordings loaded (%s)", type(error).__name__)
        return {}
    loaded, skipped = {}, 0
    for entry in entries if isinstance(entries, list) else []:
        ok = (isinstance(entry, dict) and entry.get("status") == "approved" and entry.get("intent") in PROSE_INTENTS
              and isinstance(entry.get("subject"), str) and isinstance(entry.get("input_sha256"), str)
              and entry.get("format_identity") == text_format.FORMAT_IDENTITY and valid_sections(entry.get("sections"))
              and entry.get("output_sha256") == sections_digest(entry["sections"]))
        if ok:
            loaded[(entry["subject"], entry["intent"])] = entry
        else:
            skipped += 1
    logger.info("Rewordings loaded: %d approved, %d skipped", len(loaded), skipped)
    return loaded


# (sentence template, separator, values are entity terms)
FORMATS = {
    "disease_symptom": ("The symptoms of {0} include: {1}", ", ", True),
    "symptom_disease": ("Diseases recorded as associated with symptom {0}: {1}. This is not a diagnosis.", ", ", True),
    "disease_prevention": ("Precautions for {0} include: {1}", "; ", False),
    "disease_cause": ("The possible causes of {0} are: {1}", "; ", False),
    "disease_cure_way": ("Treatments recorded for {0}: {1}. This is not medical advice.", "; ", True),
    "disease_description": ("Description recorded for {0}: {1}", "; ", False),
    "disease_accompany": ("Accompanying conditions recorded for {0}: {1}", "; ", True),
}


class AnswerSearcher:
    rewordings = {}  # set in __init__; a searcher built otherwise (tests, the offline harness) serves none

    def __init__(self, driver=None):
        self.driver = driver if driver is not None else database.create_driver(**database.API_DRIVER_SETTINGS)
        self.num_limit = 20
        self.query_timeout = database.query_timeout()
        self.rewordings = load_rewordings()

    def close(self):
        self.driver.close()

    def readiness(self, owner, plan_hash):
        """(importer-owned diseases, those stamped with plan_hash): one read, no retries, a timeout of at most 1 s."""
        query = Query(READINESS_QUERY, timeout=min(self.query_timeout, READINESS_TIMEOUT))
        with self.driver.session(database=database.database_name(), default_access_mode=READ_ACCESS) as session:
            record = session.run(query, {"owner": owner, "plan": plan_hash}).single(strict=True)
        return record["diseases"], record["matching"]

    def group_values(self, question_type, answers):
        """{subject: sorted usable values} for one intent, capped at num_limit values each."""
        _, _, terms_only = FORMATS[question_type]
        grouped = {}
        for row in answers:
            values = row.get("value")
            values = values if isinstance(values, list) else [values]
            usable = grouped.setdefault(row.get("subject"), set())
            for value in values:
                if isinstance(value, str) and value.strip() and (not terms_only or is_valid_term(value)):
                    usable.add(value.strip())
        return {
            subject: sorted(values)[:self.num_limit]
            for subject, values in sorted(grouped.items(), key=lambda item: str(item[0]))
            if subject and values
        }

    def answer_prettify(self, question_type, answers):
        if question_type not in FORMATS:
            return []
        template, separator, _ = FORMATS[question_type]
        return [template.format(subject, separator.join(values)) for subject, values in self.group_values(question_type, answers).items()]

    def structure(self, question_type, answers):
        """One entry per subject: the plain sentence, plus a lead, bullet items and a note for list answers."""
        if question_type not in FORMATS:
            return []
        template, separator, terms_only = FORMATS[question_type]
        prefix, suffix = template.split("{1}")
        results = []
        for subject, values in self.group_values(question_type, answers).items():
            entry = {"intent": question_type, "subject": subject, "text": template.format(subject, separator.join(values))}
            if terms_only:
                # Lists render as bullets: "The symptoms of asthma include:" + items + an optional note.
                entry.update(lead=prefix.format(subject).strip(), items=values, note=suffix.strip(". ").strip() or None)
            else:
                # Long text keeps every word but shows its own sections and numbered points when it has them (D-028).
                found = [section for value in values for section in (text_format.sections(value) or [])]
                if found:
                    entry.update(lead=prefix.format(subject).strip(), sections=found)
                self.add_rewording(entry, subject, question_type, values)
            results.append(entry)
        return results

    def add_rewording(self, entry, subject, intent, values):
        """Attach an approved rewording only when it was made from exactly these values, with the same headings and
        segment count as the original; the original stays in the entry untouched (D-029)."""
        stored = self.rewordings.get((subject, intent))
        if not stored or stored["input_sha256"] != digest(canonical_input(subject, intent, values)):
            return
        original = text_format.prose_segments(values)
        if [s["heading"] for s in original] != [s["heading"] for s in stored["sections"]] or len(original) != len(stored["sections"]):
            return
        entry.update(lead=entry.get("lead") or FORMATS[intent][0].split("{1}")[0].format(subject).strip(),
                     reworded=True, reworded_sections=stored["sections"])

    def run(self, sqls):
        """Run each intent's queries; returns [(question_type, rows)]."""
        results = []
        for _sql in sqls:
            answers = []
            for query, params in _sql["sql"]:
                records, _, _ = self.driver.execute_query(
                    Query(query, timeout=self.query_timeout),
                    parameters_=params,
                    database_=database.database_name(),
                    routing_=RoutingControl.READ,
                )
                answers += [record.data() for record in records]
            logger.debug("Intent %s: %d query(ies) returned %d row(s)", _sql["question_type"], len(_sql["sql"]), len(answers))
            results.append((_sql["question_type"], answers))
        return results

    def search_main(self, sqls):
        return [sentence for question_type, rows in self.run(sqls) for sentence in self.answer_prettify(question_type, rows)]

    def search_structured(self, sqls):
        return [entry for question_type, rows in self.run(sqls) for entry in self.structure(question_type, rows)]
