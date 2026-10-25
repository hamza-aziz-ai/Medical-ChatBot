import json
import logging
import re
from pathlib import Path

from answer_searcher import AnswerSearcher
from question_classifier import ENTITIES_PATH, QuestionClassifier
from question_parser import ENTITY_TYPES, QuestionParser

logger = logging.getLogger(__name__)

ABSTENTION = (
    "I cannot answer this question from the available medical knowledge graph. "
    "Please consult a qualified medical professional."
)
CONSULT = "Please consult a qualified medical professional."

# Why the bot could not answer, in words the user can act on (D-015).
ABSTAIN_REASONS = {
    "no_entity": "I couldn't find a disease or symptom I know in your question.",
    "unsupported_question": (
        "I can't answer questions about how long an illness lasts, the chance of a cure, "
        "or who is likely to get it: the knowledge graph doesn't record them."
    ),
    "unsupported_entity": "I know that as a medical department, but I can only answer questions about diseases and symptoms.",
    "no_facts": "The knowledge graph has nothing recorded for that question.",
}

UNSUPPORTED_INTENTS = frozenset({
    "disease_last_time",
    "disease_cure_probability",
    "disease_easy_get",
})

INTENT_LABELS = {
    "disease_symptom": "Symptoms",
    "disease_cause": "Causes",
    "disease_prevention": "Prevention",
    "disease_cure_way": "Treatments",
    "disease_accompany": "Complications",
    "disease_description": "Description",
    "symptom_disease": "Diseases with this symptom",
    "disease_last_time": "How long it lasts",
    "disease_cure_probability": "Chance of a cure",
    "disease_easy_get": "Who gets it",
}

# How a suggestion chip asks each question. A chip is only offered when its question classifies back to
# exactly this intent for that name (some names contain intent keywords, such as "infection").
QUESTION_FOR = {
    "disease_symptom": "What are the symptoms of {}?",
    "disease_cause": "What causes {}?",
    "disease_prevention": "How can I prevent {}?",
    "disease_cure_way": "How is {} treated?",
    "disease_accompany": "What are the complications of {}?",
    "disease_description": "What is {}?",
    "symptom_disease": "Which diseases have the symptom {}?",
}
MAX_SUGGESTIONS = 3
MEDICAL_TYPES = ("disease", "symptom")

# A follow-up may reuse the confirmed topic only if it refers back ("what causes it?") or continues
# ("and prevention?") and every other word is filler or an intent keyword. Anything else, including
# digits or non-English words, may name another subject, so the topic is not reused.
REFERENCE_WORDS = frozenset("it its this that these those they them".split())
FILLER = frozenset("""
a an the of for to is are was were be been what which how can could i do does did about and me my tell there any
with in on should we you please get got have has had from or by up so more some
""".split()) | REFERENCE_WORDS
PUNCTUATION = "?.!,;:'\"()"


def replace_phrase(question, phrase, replacement):
    """The question with one whole-word phrase replaced, ignoring case."""
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"(?!\w)"
    return re.sub(pattern, lambda _: replacement, question, count=1, flags=re.IGNORECASE)


class ChatBotGraph:
    def __init__(self):
        self.classifier = QuestionClassifier()
        self.parser = QuestionParser()
        self.searcher = AnswerSearcher()
        self.availability = self.load_availability()
        logger.info("Chatbot ready: %d disease, %d symptom and %d department terms loaded",
                    len(self.classifier.disease_words), len(self.classifier.symptom_words), len(self.classifier.department_words))

    @staticmethod
    def load_availability(path=ENTITIES_PATH):
        """Which intents have facts, per disease, as written by the importer next to the dictionary.

        Reading a file means no database call at start or per request; it changes only with a re-import,
        which already needs an API restart for the dictionary itself.
        """
        try:
            with open(path, encoding="utf-8") as file:
                table = json.load(file).get("intents") or {}
        except (OSError, ValueError) as error:
            logger.warning("Suggestions disabled: cannot read intents from %s (%s)", Path(path).name, type(error).__name__)
            return {}
        if not table:
            logger.warning("Suggestions disabled: %s has no intents table; re-run the importer", Path(path).name)
        else:
            logger.info("Loaded answerable intents for %d diseases", len(table))
        return table

    def chat_main(self, sent):
        return self.respond(sent)["message"]

    def respond(self, question, topic=None, selections=()):
        """Answer one question as a structured reply (D-015).

        topic is the confirmed {"name", "type"} from the previous answer, used for follow-ups and to read a name
        that is both a disease and a symptom. selections are the {name, type} choices the user made while
        clarifying this same question. Log intent names and counts only: names come from the user.
        """
        topic = self.valid_topic(topic)
        alias_hits = []
        arguments = self.classifier.check_medical(question.lower(), alias_hits)
        ambiguous_alias = next((hit for hit in alias_hits if len(hit["names"]) > 1), None)
        if ambiguous_alias:
            logger.info("Clarifying: an alias names several entries")
            return self.clarify_alias(question, ambiguous_alias)
        used_topic = False
        if not arguments and topic and self.is_follow_up(question):
            arguments, used_topic = {topic["name"]: [topic["type"]]}, True
        if not arguments:
            typos = self.classifier.close_matches(self.unexplained_phrases(question))
            if typos:
                # Offered, never applied: the user confirms by choosing (step 2 of D-015).
                logger.info("Clarifying: %d possible spelling(s) offered", len(typos))
                return self.clarify_typo(question, typos)
            logger.info("Abstained: no known entity in the question")
            return self.abstain("no_entity")

        chosen = self.valid_selections(selections, arguments)
        for name in arguments:
            if name in chosen:
                arguments[name] = [chosen[name]]
            elif topic and name == topic["name"] and topic["type"] in arguments[name]:
                arguments[name] = [topic["type"]]
        classified = self.classifier.classify_with(question, arguments)
        intents = classified["question_types"]
        interpretation = self.interpretation(arguments, intents, used_topic, alias_hits)
        topic_out = self.single_topic(arguments, intents)
        logger.debug("Classified %d entit(ies) with intents %s (topic used: %s)", len(arguments), intents, used_topic)

        # The veto comes first and needs no database: a clarification must not hide an unsupported question.
        if UNSUPPORTED_INTENTS.intersection(intents):
            logger.info("Abstained: unsupported intent %s", sorted(UNSUPPORTED_INTENTS.intersection(intents)))
            return self.abstain("unsupported_question", interpretation, topic_out)
        if not intents and all(set(types) <= {"department"} for types in arguments.values()):
            logger.info("Abstained: department-only question")
            return self.abstain("unsupported_entity", interpretation)

        ambiguous = [name for name, types in arguments.items() if set(MEDICAL_TYPES) <= set(types)]
        if ambiguous and {"disease_symptom", "symptom_disease"} <= set(intents):
            logger.info("Clarifying: a name is both a disease and a symptom")
            return self.clarify(question, ambiguous[0], chosen, interpretation)

        answers = self.searcher.search_structured(self.parser.parser_main(classified)) if intents else []
        if not answers:
            logger.info("Abstained: the graph had no answer for intents %s", intents)
            return self.abstain("no_facts", interpretation, topic_out, suggest=True)
        for answer in answers:
            answer["label"] = INTENT_LABELS[answer["intent"]]
        logger.info("Answered with %d result(s) for intents %s", len(answers), intents)
        defaulted = intents == ["disease_description"] and not self.classifier.has_intent_keyword(question)
        return self.reply(
            "answer", "default_description" if defaulted else "answered",
            "\n".join(answer["text"] for answer in answers),
            answers=answers, topic=topic_out, interpretation=interpretation,
            options=self.suggestions(topic_out, exclude=intents),
        )

    def valid_topic(self, topic):
        if not isinstance(topic, dict) or not isinstance(topic.get("name"), str) or topic.get("type") not in MEDICAL_TYPES:
            return None
        types = self.classifier.word_type_dictionary.get(topic["name"])
        return {"name": topic["name"], "type": topic["type"]} if types and topic["type"] in types else None

    @staticmethod
    def valid_selections(selections, arguments):
        """Only choices about names found in this question, for a type that name really has."""
        chosen = {}
        for selection in selections or ():
            if not isinstance(selection, dict):
                continue
            name, entity_type = selection.get("name"), selection.get("type")
            if entity_type in MEDICAL_TYPES and entity_type in arguments.get(name, ()):
                chosen[name] = entity_type
        return chosen

    def unexplained_phrases(self, question):
        """Runs of 1-3 words that are neither filler nor intent keywords: the candidates for a misspelled name."""
        keywords = {word for phrase in self.classifier.intent_keywords() for word in phrase.lower().split()}
        runs, run = [], []
        for token in (token.strip(PUNCTUATION) for token in question.lower().split()):
            if token and token not in FILLER and token not in keywords:
                run.append(token)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        phrases = []
        for run in runs:
            for size in (3, 2, 1):
                phrases += [" ".join(run[i:i + size]) for i in range(len(run) - size + 1)]
        return phrases

    def clarify_typo(self, question, typos):
        names = " or ".join(f'"{name}"' for _, name in typos)
        options = [{"label": name, "question": replace_phrase(question, phrase, name)} for phrase, name in typos]
        return self.reply("clarify", "possible_typo", f"I don't recognise that name. Did you mean {names}?", options=options)

    def clarify_alias(self, question, hit):
        options = [{"label": target["name"], "question": replace_phrase(question, hit["alias"], target["name"])} for target in hit["names"]]
        return self.reply("clarify", "ambiguous_alias", f'"{hit["alias"]}" can mean more than one thing. Which did you mean?', options=options)

    def is_follow_up(self, question):
        """True for "what causes it?" or "and prevention?"; false as soon as any word could name a subject."""
        tokens = [token.strip(PUNCTUATION) for token in question.lower().split()]
        tokens = [token for token in tokens if token]
        continues = tokens[:1] == ["and"] or tokens[:2] in (["what", "about"], ["how", "about"])
        if not (continues or REFERENCE_WORDS.intersection(tokens)):
            return False
        keywords = {word for phrase in self.classifier.intent_keywords() for word in phrase.lower().split()}
        return all(token in FILLER or token in keywords for token in tokens)

    @staticmethod
    def single_topic(arguments, intents):
        """The one subject a follow-up can refer to, or None when the question named several."""
        if len(arguments) != 1:
            return None
        (name, types), = arguments.items()
        wanted = {ENTITY_TYPES.get(intent) for intent in intents} & set(types) or set(types) & set(MEDICAL_TYPES)
        return {"name": name, "type": wanted.pop()} if len(wanted) == 1 else None

    def suggestions(self, topic, exclude=()):
        if not topic:
            return []
        if topic["type"] == "symptom":
            available = ["symptom_disease"]
        else:
            available = self.availability.get(topic["name"], [])
        options = []
        for intent in QUESTION_FOR:
            if intent in available and intent not in exclude and self.round_trips(intent, topic):
                options.append({"label": QUESTION_FOR[intent].format(topic["name"]), "question": QUESTION_FOR[intent].format(topic["name"]), "topic": topic})
        return options[:MAX_SUGGESTIONS]

    def round_trips(self, intent, topic):
        question = QUESTION_FOR[intent].format(topic["name"])
        return self.classifier.classify_with(question, {topic["name"]: [topic["type"]]})["question_types"] == [intent]

    def clarify(self, question, name, chosen, interpretation):
        options = []
        for entity_type in MEDICAL_TYPES:
            picked = [{"name": n, "type": t} for n, t in chosen.items()] + [{"name": name, "type": entity_type}]
            options.append({"label": f"{name} as a {entity_type}", "question": question, "selections": picked})
        return self.reply(
            "clarify", "ambiguous_type", f"Do you mean {name} as a disease or as a symptom?",
            interpretation=interpretation, options=options,
        )

    @staticmethod
    def interpretation(arguments, intents, used_topic, alias_hits=()):
        return {
            "entities": [{"name": name, "types": types} for name, types in arguments.items()],
            "intents": [{"intent": intent, "label": INTENT_LABELS.get(intent, intent)} for intent in intents],
            "used_topic": used_topic,
            "aliases": [{"alias": hit["alias"], "name": hit["names"][0]["name"]} for hit in alias_hits if len(hit["names"]) == 1],
        }

    def abstain(self, reason, interpretation=None, topic=None, suggest=False):
        return self.reply(
            "abstain", reason, f"{ABSTAIN_REASONS[reason]} {CONSULT}",
            topic=topic, interpretation=interpretation, options=self.suggestions(topic) if suggest else (),
        )

    @staticmethod
    def reply(status, reason, message, answers=(), topic=None, interpretation=None, options=()):
        return {
            "status": status,
            "reason": reason,
            "message": message,
            "answers": list(answers),
            "topic": topic,
            "interpretation": interpretation,
            "options": list(options),
        }
