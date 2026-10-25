import logging

from neo4j import Query, RoutingControl

import database
from terms import is_valid_term

logger = logging.getLogger(__name__)

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
    def __init__(self, driver=None):
        self.driver = driver if driver is not None else database.create_driver()
        self.num_limit = 20
        self.query_timeout = database.query_timeout()

    def close(self):
        self.driver.close()

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
            results.append(entry)
        return results

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
