from neo4j import RoutingControl

import database
from terms import is_valid_term

# (sentence template, separator, values are entity terms)
FORMATS = {
    "disease_symptom": ("The symptoms of {0} include: {1}", ", ", True),
    "symptom_disease": ("Diseases recorded as associated with symptom {0}: {1}. This is not a diagnosis.", ", ", True),
    "disease_prevention": ("Precautions for {0} include: {1}", "; ", False),
    "disease_cause": ("The possible causes of {0} are: {1}", "; ", False),
    "disease_cure_way": ("For {0}, you can try the following treatments: {1}", "; ", True),
    "disease_description": ("{0}, familiar with: {1}", "; ", False),
    "disease_accompany": ("Accompanying conditions recorded for {0}: {1}", "; ", True),
}


class AnswerSearcher:
    def __init__(self, driver=None):
        self.driver = driver if driver is not None else database.create_driver()
        self.num_limit = 20

    def close(self):
        self.driver.close()

    def answer_prettify(self, question_type, answers):
        if question_type not in FORMATS:
            return []

        template, separator, terms_only = FORMATS[question_type]
        grouped = {}
        for row in answers:
            values = row.get("value")
            values = values if isinstance(values, list) else [values]
            usable = grouped.setdefault(row.get("subject"), set())
            for value in values:
                if isinstance(value, str) and value.strip() and (not terms_only or is_valid_term(value)):
                    usable.add(value.strip())

        return [
            template.format(subject, separator.join(sorted(values)[:self.num_limit]))
            for subject, values in sorted(grouped.items(), key=lambda item: str(item[0]))
            if subject and values
        ]

    def search_main(self, sqls):
        final_answers = []
        for _sql in sqls:
            answers = []
            for query, params in _sql["sql"]:
                records, _, _ = self.driver.execute_query(
                    query,
                    parameters_=params,
                    database_=database.database_name(),
                    routing_=RoutingControl.READ,
                )
                answers += [record.data() for record in records]
            final_answers += self.answer_prettify(_sql["question_type"], answers)

        return final_answers
