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
        if entities:
            sql = []

            if question_type == "disease_cause":
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.causes".format(i) for i in entities]

            elif question_type == 'disease_prevention':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.prevention".format(i) for i in entities]

            elif question_type == 'disease_last_time':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.cure_last_time".format(i) for i in entities]

            elif question_type == 'disease_cure_probability':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.cured_prob".format(i) for i in entities]

            elif question_type == 'disease_cure_way':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.cure_way".format(i) for i in entities]

            elif question_type == 'disease_easy_get':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.easy_get".format(i) for i in entities]

            elif question_type == 'disease_description':
                sql = ["match (m:Disease) where m.name = '{0}' return m.name, m.description".format(i) for i in entities]

            elif question_type == 'disease_symptom':
                sql = ["match (m:Disease)-[r:has_symptom]->(n:Symptom) where m.name = '{0}' return m.name, r.name, n.name".format(i) for i in entities]

            elif question_type == 'symptom_disease':
                sql = ["match (m:Disease)-[r:has_symptom]->(n:Symptom) where n.name = '{0}' return m.name, r.name, n.name".format(i) for i in entities]

            elif question_type == 'disease_accompany':
                sql_1 = ["match (m:Disease)-[r:accompany_with]->(n:Disease) where m.name = '{0}' return m.name, r.name, n.name".format(i) for i in entities]
                sql_2 = ["match (m:Disease)-[r:accompany_with]->(n:Disease) where n.name = '{0}' return m.name, r.name, n.name".format(i) for i in entities]
                sql = sql_1 + sql_2

            return sql

        return []

    def parser_main(self, result_classify):
        arguments = result_classify["arguments"]
        entity_dictionary = self.build_entity_dictionary(arguments)
        question_types = result_classify["question_types"]
        sqls = []

        for question_type in question_types:
            _sql = {"question_type": question_type}
            sql = []

            if question_type == "disease_symptom":
                sql = self.sql_transfer(question_type, entity_dictionary.get("disease"))

            elif question_type == 'symptom_disease':
                sql = self.sql_transfer(question_type, entity_dictionary.get('symptom'))

            elif question_type == 'disease_cause':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_accompany':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_prevention':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_last_time':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_cure_way':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_cure_probability':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_easy_get':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            elif question_type == 'disease_description':
                sql = self.sql_transfer(question_type, entity_dictionary.get('disease'))

            if sql:
                _sql['sql'] = sql

                sqls.append(_sql)

        return sqls
