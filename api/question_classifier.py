import re
from pathlib import Path

import ahocorasick

from terms import is_valid_term

DICTIONARY_DIR = Path(__file__).resolve().parent / "dictionary"


def load_terms(file_name):
    with open(DICTIONARY_DIR / file_name, encoding="utf-8") as file:
        return [line.strip() for line in file if is_valid_term(line)]


def is_word_char(char):
    return char.isalnum() or char == "_"


class QuestionClassifier:
    def __init__(self):
        self.disease_words = load_terms("diseases.txt")
        self.department_words = load_terms("departments.txt")
        self.symptom_words = load_terms("symptoms.txt")

        self.region_words = set(self.department_words + self.disease_words + self. symptom_words)

        self.region_tree = self.build_acyclic_tree(list(self.region_words))
        self.word_type_dictionary = self.build_word_type_dictionary()

        self.symptom_question_words = [
            'symptom',
            'symptoms',
            'characterization',
            'characterizations',
            'phenomenon',
            'phenomena'
        ]

        self.cause_question_words = [
            'reason',
            'reasons',
            'cause',
            'causes'
        ]

        self.accompany_question_words = [
            'complication',
            'complications',
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
            'prevented',
            'resist',
            'guard',
            'against',
            'escape',
            'avoid',
            'how can i not',
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
            'treated',
            'heal',
            'healing',
            'cure',
            'cured',
            'how to treat',
            'how to heal',
            'how to cure',
            'treatment',
            'treatments',
            'therapy',
            'therapies'
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
        spans = []
        for end, (_, word) in self.region_tree.iter(question):
            start = end - len(word) + 1
            before = question[start - 1] if start > 0 else ""
            after = question[end + 1] if end + 1 < len(question) else ""
            if not (is_word_char(before) or is_word_char(after)):
                spans.append((start, end, word))

        # Drop a match only when its own occurrence lies inside another match's occurrence.
        kept = [
            span for span in spans
            if not any(other != span and other[0] <= span[0] and span[1] <= other[1] for other in spans)
        ]

        final_dictionary = {}
        for _, _, word in sorted(kept):
            final_dictionary.setdefault(word, self.word_type_dictionary.get(word))

        return final_dictionary

    @staticmethod
    def check_words(words, sent):
        sent = sent.lower()
        for word in words:
            phrase = r"\s+".join(re.escape(part) for part in word.lower().split())
            if re.search(r"(?<!\w)" + phrase + r"(?!\w)", sent):
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
