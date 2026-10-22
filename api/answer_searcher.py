import os

from py2neo import Graph


class AnswerSearcher:
    def __init__(self):
        self.graph = Graph("neo4j://localhost:7687", auth=("neo4j", os.environ["NEO4J_PASSWORD"]))
        self.num_limit = 20

    def answer_prettify(self, question_type, answers):
        final_answer = []

        if not answers:
            return ''

        if question_type == 'disease_symptom':
            description = [i['n.name'] for i in answers]
            subject = answers[0]['m.name']
            final_answer = "The symptoms of {0} include: {1}".format(subject, ', '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'symptom_disease':
            description = [i['m.name'] for i in answers]
            subject = answers[0]['n.name']
            final_answer = 'You entered symptoms as: {0}. You may be infected with: {1}'.format(subject, ', '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_prevention':
            description = [i['m.prevention'] for i in answers]
            subject = answers[0]['m.name']
            final_answer = "Precautions for {0} include: {1}".format(subject, '; '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_cause':
            description = [i['m.causes'] for i in answers]
            subject = answers[0]['m.name']
            final_answer = 'The possible causes of {0} are: {1}'.format(subject, '; '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_last_time':
            description = [i['m.cure_last_time'] for i in answers]
            subject = answers[0]['m.name']
            final_answer = 'The period in which {0} treatment may last is: {1}'.format(subject, '; '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_cure_way':
            description = ['; '.join(i['m.cure_way']) for i in answers]
            subject = answers[0]['m.name']
            final_answer = 'For {0}, you can try the following treatments: {1}'.format(subject, '; '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_description':
            description = [i['m.description'] for i in answers]
            subject = answers[0]['m.name']
            final_answer = '{0}, familiar with: {1}'.format(subject, '; '.join(list(set(description))[:self.num_limit]))

        elif question_type == 'disease_accompany':
            description_1 = [i['n.name'] for i in answers]
            description_2 = [i['m.name'] for i in answers]
            subject = answers[0]['m.name']
            description = [i for i in description_1 + description_2 if i != subject]
            final_answer = 'The symptoms of {0} include: {1}'.format(subject, '; '.join(list(set(description))[:self.num_limit]))

        return final_answer

    def search_main(self, sqls):
        final_answers = []
        for _sql in sqls:
            question_type = _sql['question_type']
            queries = _sql['sql']
            answers = []
            for query in queries:
                result = self.graph.run(query).data()
                answers = answers + result
            final_answer = self.answer_prettify(question_type, answers)
            if final_answer:
                final_answers.append(final_answer)

        return final_answers
