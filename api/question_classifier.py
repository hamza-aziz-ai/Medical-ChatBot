import os
import ahocorasick


class QuestionClassifier:
    def __init__(self):
        current_directory = '\\'.join(os.path.abspath(__file__).split('\\')[:-1])
        print(current_directory)

        self.diseases_path = os.path.join(current_directory, ".\\dictionary\\diseases.txt")
        self.departments_path = os.path.join(current_directory, ".\\dictionary\\departments.txt")
        self.symptoms_path = os.path.join(current_directory, ".\\dictionary\\symptoms.txt")

        self.disease_words = [i.strip() for i in open(self.diseases_path, 'r', encoding="gbk") if i.strip()]
        self.department_words = [i.strip() for i in open(self.departments_path, 'r', encoding="gbk") if i.strip()]
        self.symptom_words = [i.strip() for i in open(self.symptoms_path, 'r', encoding="utf-8") if i.strip()]

        self.region_words = set(self.department_words + self.disease_words + self. symptom_words)

        self.region_tree = self.build_acyclic_tree(list(self.region_words))
        self.word_type_dictionary = self.build_word_type_dictionary()

        self.symptom_question_words = [
            'symptom',
            'characterization',
            'phenomenon'
        ]

        self.cause_question_words = [
            'reason',
            'cause'
        ]

        self.accompany_question_words = [
            'complication',
            'concurrent',
            'occur',
            'happen together',
            'occur together',
            'appear together',
            'together',
            'accompany',
            'follow',
            'coexist'
        ]

        self.prevent_question_words = [
            'prevention',
            'prevent',
            'resist',
            'guard',
            'against',
            'escape',
            'avoid',
            'how can I not',
            'how not to',
            'why not',
            'how to prevent'
        ]

        self.last_time_question_words = [
            'cycle',
            'time',
            'day',
            'year',
            'hour',
            'days',
            'years',
            'hours',
            'how long',
            'how much time',
            'a few days',
            'how many years',
            'how many days',
            'how many hours',
            'a few hours',
            'a few years'
        ]

        self.cure_way_question_words = [
            'treat',
            'heal',
            'cure',
            'how to treat',
            'how to heal',
            'how to cure',
            'treatment',
            'therapy'
        ]

        self.cure_probability_question_words = [
            'how big is the hope of cure',
            'hope',
            'probability',
            'possibility',
            'percentage',
            'proportion'
        ]

        self.easy_get_question_words = [
            'susceptible population',
            'susceptible',
            'crowd',
            'easy to infect',
            'who',
            'which people',
            'infection',
            'infect'
        ]

        self.belong_question_words = [
            'what belongs to',
            'belong',
            'belongs',
            'section',
            'what section',
            'department'
        ]

        self.cure_question_words = [
            'what to treat',
            'indication',
            'what is the use',
            'benefit',
            'usefulness'
        ]

    @staticmethod
    def build_acyclic_tree(word_list):
        acyclic_tree = ahocorasick.Automaton()
        for i, word in enumerate(word_list):
            acyclic_tree.add_word(word, (i, word))
        acyclic_tree.make_automaton()

        return acyclic_tree

    def build_word_type_dictionary(self):
        word_dictionary = dict()

        for word in self.region_words:
            word_dictionary[word] = []
            if word in self.disease_words:
                word_dictionary[word].append("disease")
            if word in self.department_words:
                word_dictionary[word].append("department")
            if word in self.symptom_words:
                word_dictionary[word].append("symptom")

        return word_dictionary

    def check_medical(self, question):
        region_words = []

        for i in self.region_tree.iter(question):
            word = i[1][1]
            region_words.append(word)

        stop_words = []
        for word_1 in region_words:
            for word_2 in region_words:
                if (word_1 in word_2) and (word_1 != word_2):
                    stop_words.append(word_1)

        final_words = [i for i in region_words if i not in stop_words]
        final_dictionary = {i: self.word_type_dictionary.get(i) for i in final_words}

        return final_dictionary

    @staticmethod
    def check_words(words, sent):
        for word in words:
            if word in sent:
                return True

        return False

    def classify(self, question):
        data = {}
        question_2 = question.lower()
        medical_dictionary = self.check_medical(question_2)

        if not medical_dictionary:
            return {}

        data['arguments'] = medical_dictionary
        types = []

        for _type in medical_dictionary.values():
            types = types + _type
        # question_type = "others"

        question_types = []

        if self.check_words(self.symptom_question_words, question_2) and ("disease" in types):
            question_type = "disease_symptom"
            question_types.append(question_type)

        if self.check_words(self.symptom_question_words, question_2) and ("symptom" in types):
            question_type = "symptom_disease"
            question_types.append(question_type)

        if self.check_words(self.cause_question_words, question_2) and ("disease" in types):
            question_type = "disease_cause"
            question_types.append(question_type)

        if self.check_words(self.prevent_question_words, question_2) and ("disease" in types):
            question_type = "disease_prevention"
            question_types.append(question_type)

        if self.check_words(self.accompany_question_words, question_2) and ("disease" in types):
            question_type = "disease_accompany"
            question_types.append(question_type)

        if self.check_words(self.last_time_question_words, question_2) and ("disease" in types):
            question_type = "disease_last_time"
            question_types.append(question_type)

        if self.check_words(self.cure_way_question_words, question_2) and ("disease" in types):
            question_type = "disease_cure_way"
            question_types.append(question_type)

        if self.check_words(self.cure_probability_question_words, question_2) and ("disease" in types):
            question_type = "disease_cure_probability"
            question_types.append(question_type)

        if self.check_words(self.easy_get_question_words, question_2) and ("disease" in types):
            question_type = "disease_easy_get"
            question_types.append(question_type)

        if (question_types == []) and ("disease" in types):
            question_types = ["disease_description"]

        if (question_types == []) and ("symptom" in types):
            question_types = ["symptom_disease"]

        data["question_types"] = question_types

        return data
