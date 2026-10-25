import difflib
from itertools import groupby
import json
import logging
import re
from pathlib import Path

import ahocorasick

from terms import is_valid_term

logger = logging.getLogger(__name__)

ENTITIES_PATH = Path(__file__).resolve().parent / "dictionary" / "entities.json"
ALIASES_PATH = Path(__file__).resolve().parent / "dictionary" / "aliases.json"
# Typo suggestions: tuned on reviewed misspellings and unrelated words (see tests/test_matching.py).
TYPO_CUTOFF = 0.8
MAX_TYPO_SUGGESTIONS = 3


def load_entities(path=ENTITIES_PATH):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    entities = {key: [term.strip() for term in data[key] if is_valid_term(term)] for key in ("diseases", "departments", "symptoms")}
    logger.info("Loaded %s from %s", ", ".join(f"{len(v)} {k}" for k, v in entities.items()), Path(path).name)
    return entities


def load_aliases(names_by_type, path=ALIASES_PATH):
    """{alias: [(name, type), ...]} for aliases whose target exists with that type; others are skipped and logged."""
    try:
        with open(path, encoding="utf-8") as file:
            entries = json.load(file).get("aliases", [])
    except (OSError, ValueError) as error:
        logger.warning("No aliases loaded from %s (%s)", Path(path).name, type(error).__name__)
        return {}
    known = {name for names in names_by_type.values() for name in names}
    aliases = {}
    for entry in entries:
        alias, name, entity_type = (str(entry.get(key, "")).strip().lower() for key in ("alias", "name", "type"))
        if not alias or alias in known or name not in names_by_type.get(entity_type, ()):
            logger.warning("Skipped an alias whose target is not a %s in the dictionary", entity_type or "known type")
            continue
        targets = aliases.setdefault(alias, [])
        if (name, entity_type) not in targets:
            targets.append((name, entity_type))
    logger.info("Loaded %d alias(es) from %s", len(aliases), Path(path).name)
    return aliases


def is_word_char(char):
    return char.isalnum() or char == "_"


class QuestionClassifier:
    def __init__(self):
        entities = load_entities()
        self.disease_words = entities["diseases"]
        self.department_words = entities["departments"]
        self.symptom_words = entities["symptoms"]

        self.region_words = set(self.department_words + self.disease_words + self. symptom_words)
        # Sourced other names ("whooping cough" -> pertussis). Matched like names, reported in the interpretation.
        self.aliases = load_aliases({"disease": set(self.disease_words), "symptom": set(self.symptom_words)})

        self.region_tree = self.build_acyclic_tree(list(self.region_words | set(self.aliases)))
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

    def entity_spans(self, question):
        """(start, end, word) for every name or alias occurring as a whole word in the lowercased question."""
        spans = []
        for end, (_, word) in self.region_tree.iter(question):
            start = end - len(word) + 1
            before = question[start - 1] if start > 0 else ""
            after = question[end + 1] if end + 1 < len(question) else ""
            if not (is_word_char(before) or is_word_char(after)):
                spans.append((start, end, word))
        return spans

    def mask_entities(self, question):
        """The lowercased question with each run of entity names replaced by '#', so their words are not read as intent keywords (BUG-002).

        '#' is neither a word character nor a space, so a keyword phrase cannot bridge a masked name.
        A name that is itself an intent keyword ("phenomenon") stays readable as one, which keeps today's behaviour.
        """
        question = question.lower()
        keywords = {keyword.lower() for keyword in self.intent_keywords()}
        covered = [False] * len(question)
        for start, end, word in self.entity_spans(question):
            if word not in keywords:
                covered[start:end + 1] = [True] * (end + 1 - start)
        runs = groupby(zip(question, covered), key=lambda pair: pair[1])
        return "".join("#" if hidden else "".join(char for char, _ in run) for hidden, run in runs)

    def check_medical(self, question, alias_hits=None):
        spans = self.entity_spans(question)

        # Drop a match only when its own occurrence lies inside another match's occurrence.
        kept = [
            span for span in spans
            if not any(other != span and other[0] <= span[0] and span[1] <= other[1] for other in spans)
        ]

        final_dictionary = {}
        for _, _, word in sorted(kept):
            if word in self.word_type_dictionary:
                final_dictionary.setdefault(word, self.word_type_dictionary.get(word))
                continue
            targets = self.aliases[word]
            if alias_hits is not None:
                alias_hits.append({"alias": word, "names": [{"name": name, "type": t} for name, t in targets]})
            if len(targets) == 1:
                (name, entity_type), = targets
                final_dictionary.setdefault(name, [entity_type])

        return final_dictionary

    def close_matches(self, words, accept=lambda sequence, name: True):
        """Dictionary names close to the given word sequences, as (sequence, name) pairs in first-seen order.

        Each name keeps the sequence it matches best, scored as difflib does, so a longer window that merely
        contains the misspelling ("causes adbominal infection") never replaces the one that is the misspelling.
        """
        names = sorted(set(self.disease_words) | set(self.symptom_words) | set(self.aliases))
        best = {}
        for sequence in words:
            for name in difflib.get_close_matches(sequence, names, n=MAX_TYPO_SUGGESTIONS, cutoff=TYPO_CUTOFF):
                if not accept(sequence, name):
                    continue
                score = difflib.SequenceMatcher(None, name, sequence).ratio()
                if name not in best or score > best[name][0]:
                    best[name] = (score, sequence)
        return [(sequence, name) for name, (_, sequence) in best.items()][:MAX_TYPO_SUGGESTIONS]

    @staticmethod
    def check_words(words, sent):
        sent = sent.lower()
        for word in words:
            phrase = r"\s+".join(re.escape(part) for part in word.lower().split())
            if re.search(r"(?<!\w)" + phrase + r"(?!\w)", sent):
                return True

        return False

    def intent_keywords(self):
        return [phrase for name, words in vars(self).items() if name.endswith("_question_words") for phrase in words]

    def has_intent_keyword(self, question):
        return self.check_words(self.intent_keywords(), self.mask_entities(question))

    def classify(self, question):
        medical_dictionary = self.check_medical(question.lower())

        if not medical_dictionary:
            logger.debug("No known entity found")
            return {}

        return self.classify_with(question, medical_dictionary)

    def classify_with(self, question, medical_dictionary):
        """Intents for a question whose entities (name -> types) are already known."""
        data = {}
        question_2 = self.mask_entities(question)
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
        # Entity names come from the user's question, so log only counts and intent names.
        logger.debug("Found %d entit(ies); intents %s", len(medical_dictionary), question_types)
        return data
