LIMIT = 20

# Labels, relationship types and property names are fixed here; entity names are always parameters.
TEMPLATES = {
    "disease_cause": "MATCH (m:Disease {name: $name}) RETURN m.name AS subject, m.causes AS value LIMIT $limit",
    "disease_prevention": "MATCH (m:Disease {name: $name}) RETURN m.name AS subject, m.prevention AS value LIMIT $limit",
    "disease_cure_way": (
        "MATCH (m:Disease {name: $name}) UNWIND m.cure_way AS value "
        "RETURN DISTINCT m.name AS subject, value ORDER BY subject, value LIMIT $limit"
    ),
    "disease_description": "MATCH (m:Disease {name: $name}) RETURN m.name AS subject, m.description AS value LIMIT $limit",
    "disease_symptom": (
        "MATCH (m:Disease {name: $name})-[:has_symptom]->(n:Symptom) "
        "RETURN DISTINCT m.name AS subject, n.name AS value ORDER BY subject, value LIMIT $limit"
    ),
    "symptom_disease": (
        "MATCH (m:Disease)-[:has_symptom]->(n:Symptom {name: $name}) "
        "RETURN DISTINCT n.name AS subject, m.name AS value ORDER BY subject, value LIMIT $limit"
    ),
    "disease_accompany": (
        "MATCH (m:Disease {name: $name})-[:accompany_with]-(n:Disease) WHERE n.name <> m.name "
        "RETURN DISTINCT m.name AS subject, n.name AS value ORDER BY subject, value LIMIT $limit"
    ),
}

ENTITY_TYPES = {question_type: "disease" for question_type in TEMPLATES}
ENTITY_TYPES["symptom_disease"] = "symptom"


class QuestionParser:
    @staticmethod
    def build_entity_dictionary(arguments):
        entity_dictionary = {}
        for argument, types in arguments.items():
            for _type in types:
                if _type not in entity_dictionary:
                    entity_dictionary[_type] = [argument]
                else:
                    entity_dictionary[_type].append(argument)

        return entity_dictionary

    @staticmethod
    def sql_transfer(question_type, entities):
        template = TEMPLATES.get(question_type)
        if not template or not entities:
            return []

        return [(template, {"name": entity, "limit": LIMIT}) for entity in entities]

    def parser_main(self, result_classify):
        entity_dictionary = self.build_entity_dictionary(result_classify["arguments"])
        sqls = []

        for question_type in result_classify["question_types"]:
            entity_type = ENTITY_TYPES.get(question_type)
            sql = self.sql_transfer(question_type, entity_dictionary.get(entity_type))
            if sql:
                sqls.append({"question_type": question_type, "sql": sql})

        return sqls
