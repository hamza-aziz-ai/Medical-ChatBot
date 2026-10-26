import json
import logging
import re
import threading
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError

from answer_searcher import AnswerSearcher
from build_medicalgraph import OWNER
import question_classifier
from question_classifier import ENTITIES_PATH, TYPO_BUDGET_SECONDS, QuestionClassifier, read_dictionary
from question_parser import ENTITY_TYPES, QuestionParser
from understanding import Understanding, build_candidates

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
    "outside_scope": (
        "I can only say what a disease's symptoms, causes, prevention, treatments, complications or description are, "
        "or which diseases a symptom can point to."
    ),
}
UNCLEAR_SUBJECT = "Which disease or symptom do you mean? Please name it in your question."

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
SHA256 = re.compile(r"[0-9a-f]{64}")
PUNCTUATION = "?.!,;:'\"()"


# D-025: each client address gets this much spelling-suggestion time: a one-second burst, refilled at one second
# per minute. Starting values, not tuned ones.
SUGGESTION_CAPACITY_SECONDS = 1.0
SUGGESTION_REFILL_PER_SECOND = 1.0 / 60
MAX_SUGGESTION_CLIENTS = 10_000


class SuggestionBudget:
    """Per-address allowance of elapsed fuzzy-matching time (A-14, D-025), so one client cannot keep the single
    worker busy with long questions of unknown words. Addresses stay in this process's memory: never logged,
    stored or returned.
    """

    def __init__(self, clock=None, capacity=SUGGESTION_CAPACITY_SECONDS, refill=SUGGESTION_REFILL_PER_SECOND,
                 max_clients=MAX_SUGGESTION_CLIENTS):
        # The same clock close_matches checks its deadline against.
        self.clock = clock or (lambda: question_classifier.monotonic())
        self.capacity, self.refill, self.max_clients = capacity, refill, max_clients
        self.clients = {}  # address -> [credit, time of last update]; credit may be negative (debt)
        self.lock = threading.Lock()
        self.denying = False

    def credit(self, entry, now):
        return min(self.capacity, entry[0] + (now - entry[1]) * self.refill)

    def entry_for(self, client, now):
        """The client's entry with credit brought up to date, or None when the table is full of clients still owing."""
        entry = self.clients.get(client)
        if entry is None:
            if len(self.clients) >= self.max_clients:
                # Only idle, fully refilled clients are forgotten: forgetting a debtor would hand it fresh credit.
                full = [key for key, value in self.clients.items() if self.credit(value, now) >= self.capacity]
                for key in full:
                    del self.clients[key]
                if len(self.clients) >= self.max_clients:
                    return None
            entry = self.clients[client] = [self.capacity, now]
        entry[0], entry[1] = self.credit(entry, now), now
        return entry

    def run(self, client, work):
        """work(deadline) within the client's remaining credit, or None (no suggestions) when it has none.

        The deadline is set before any preparation, and the whole section holds one lock, so two requests never
        spend the same credit. Elapsed time is charged even if work fails; an overrun is carried as debt.
        """
        with self.lock:
            start = self.clock()
            entry = self.entry_for(client, start)
            if entry is None or entry[0] <= 0:
                if not self.denying:
                    logger.info("Spelling suggestions skipped: a client is over its budget")
                    self.denying = True
                return None
            self.denying = False
            try:
                return work(start + min(TYPO_BUDGET_SECONDS, entry[0]))
            finally:
                end = self.clock()
                entry[0], entry[1] = self.credit(entry, end) - (end - start), end


def edge_words_match(window, name, keywords):
    """A filler word or intent keyword at either edge of the window must also be a word of the name. "of pneumonia"
    scores close to "shock pneumonia" only because of "of", and "causes adbominal infection" would drop "causes"
    from the corrected question; "hepatitsi a" for "hepatitis a" and "deep plam infection" keep their edge words."""
    words, name_words = window.split(), set(name.split())
    edges = {word.strip(PUNCTUATION) for word in (words[0], words[-1])}
    return all(word in name_words for word in edges if word in FILLER or word in keywords)


def replace_phrase(question, phrase, replacement):
    """The question with one whole-word phrase replaced, ignoring case."""
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"(?!\w)"
    return re.sub(pattern, lambda _: replacement, question, count=1, flags=re.IGNORECASE)


class ChatBotGraph:
    understanding = None  # set in __init__; a bot built without it (some tests) uses the rules only

    def __init__(self):
        # D35: one read of the dictionary, so the classifier, the suggestions and readiness can never come from two
        # versions of the file if the importer replaces it while the API starts.
        document = read_dictionary()
        self.classifier = QuestionClassifier(document)
        self.parser = QuestionParser()
        self.searcher = AnswerSearcher()
        self.availability = self.load_availability(document=document)
        self.source = self.load_source(document=document)
        self.suggestion_budget = SuggestionBudget()
        self.understanding = Understanding()
        logger.info("Chatbot ready: %d disease, %d symptom and %d department terms loaded",
                    len(self.classifier.disease_words), len(self.classifier.symptom_words), len(self.classifier.department_words))

    @staticmethod
    def load_source(path=ENTITIES_PATH, document=None):
        """The dictionary's plan fingerprint and disease count, which the graph must match to be ready (D-022, D-023)."""
        try:
            data = document if document is not None else read_dictionary(path)
        except (OSError, ValueError) as error:
            logger.warning("Readiness unknown: cannot read %s (%s)", Path(path).name, type(error).__name__)
            return None
        plan_hash, diseases = data.get("plan_sha256"), data.get("diseases")
        if not (isinstance(plan_hash, str) and SHA256.fullmatch(plan_hash) and isinstance(diseases, list) and diseases):
            logger.warning("Readiness unknown: %s has no plan fingerprint or diseases", Path(path).name)
            return None
        return {"plan": plan_hash, "diseases": len(diseases)}

    def ready(self):
        """(ready, reason): every importer-owned disease carries the plan fingerprint of the dictionary this API
        loaded, and their number is the dictionary's. Never raises.

        The fingerprint names the intended snapshot (graph, dictionary and write queries); it does not prove the live
        graph was not damaged after the import, which the evaluator's structural checks cover.
        """
        if not self.source:
            return False, "dictionary has no source"
        try:
            diseases, matching = self.searcher.readiness(OWNER, self.source["plan"])
        except (Neo4jError, DriverError, OSError):
            return False, "graph unreachable"
        if diseases == matching == self.source["diseases"]:
            return True, None
        return False, "graph does not match the dictionary"

    @staticmethod
    def load_availability(path=ENTITIES_PATH, document=None):
        """Which intents have facts, per disease, as written by the importer next to the dictionary.

        Reading a file means no database call at start or per request; it changes only with a re-import,
        which already needs an API restart for the dictionary itself.
        """
        try:
            table = (document if document is not None else read_dictionary(path)).get("intents") or {}
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

    def respond(self, question, topic=None, selections=(), client=None):
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
            keywords = self.keyword_words()

            def suggest(deadline):
                return self.classifier.close_matches(self.unexplained_phrases(question), deadline=deadline,
                                                     accept=lambda window, name: edge_words_match(window, name, keywords))

            # Web requests spend their client's allowance (D-025); internal callers keep only the per-call deadline.
            typos = suggest(None) if client is None else self.suggestion_budget.run(client, suggest) or []
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

        # D-027: every confirmation and veto above is local and needs no graph. Only now may the language model route
        # the question; a valid reply wins (its refusals included), anything else falls through to the rules below.
        if self.understanding and self.understanding.enabled:
            candidates = build_candidates(arguments, used_topic)
            routed = self.understanding.route(question, candidates, client)
            if routed:
                return self.respond_routed(routed, candidates, used_topic, alias_hits)

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
        """Every 1-3-word window holding a word that is neither filler nor an intent keyword: the candidates for a
        misspelled name. Windows may contain filler and keywords, so names such as "deep palm infection" or
        "face of bruises" stay whole (A-13), and keep their inner punctuation so replace_phrase can find them.
        Ordered by position, every size at a position before the next, so when the time budget in close_matches
        cuts the scan short it drops the end of the question, not every single-word typo (A-14)."""
        keywords = self.keyword_words()
        tokens = question.lower().split()
        phrases = {}
        for i in range(len(tokens)):
            for size in (3, 2, 1):
                window = tokens[i:i + size]
                if len(window) < size:
                    continue
                phrase = " ".join(window).strip(PUNCTUATION)
                bare = (token.strip(PUNCTUATION) for token in window)
                if phrase and any(word and word not in FILLER and word not in keywords for word in bare):
                    phrases.setdefault(phrase)
        return list(phrases)

    def keyword_words(self):
        return {word for phrase in self.classifier.intent_keywords() for word in phrase.lower().split()}

    def respond_routed(self, routed, candidates, used_topic, alias_hits):
        """A valid model routing (D-027): an answer runs the fixed query of each (intent, subject) pair, never the
        rules' cross-product; a refusal or a clarification is final, whatever the rules would have said."""
        decision, checked = routed
        provenance = {"entities": [], "intents": [], "used_topic": used_topic, "aliases": [], "understood_by": "model"}
        if decision == "clarify":
            return self.reply("clarify", "unclear_subject", UNCLEAR_SUBJECT, interpretation=provenance)
        if decision == "unsupported":
            reason = "unsupported_question" if any(intent in UNSUPPORTED_INTENTS for intent, _ in checked) else "outside_scope"
            return self.abstain(reason, provenance, self.declined_topic(candidates, checked))
        subjects = sorted({(c["name"], c["type"]) for _, c in checked})
        names_by_intent = {}
        for intent, name in sorted({(intent, c["name"]) for intent, c in checked}):
            names_by_intent.setdefault(intent, []).append(name)
        intents = list(names_by_intent)
        selected = {name for name, _ in subjects}
        interpretation = self.interpretation({name: [t] for name, t in subjects}, intents, used_topic,
                                             [hit for hit in alias_hits if hit["names"][0]["name"] in selected])
        interpretation["understood_by"] = "model"
        topic_out = {"name": subjects[0][0], "type": subjects[0][1]} if len(subjects) == 1 else None
        sqls = [{"question_type": intent, "sql": self.parser.sql_transfer(intent, names)} for intent, names in names_by_intent.items()]
        answers = self.searcher.search_structured(sqls)
        if not answers:
            logger.info("Abstained: the graph had no answer for the model's intents %s", intents)
            return self.abstain("no_facts", interpretation, topic_out, suggest=True)
        for answer in answers:
            answer["label"] = INTENT_LABELS[answer["intent"]]
        logger.info("Answered with %d result(s) for the model's intents %s", len(answers), intents)
        return self.reply(
            "answer", "answered", "\n".join(answer["text"] for answer in answers),
            answers=answers, topic=topic_out, interpretation=interpretation,
            options=self.suggestions(topic_out, exclude=intents),
        )

    @staticmethod
    def declined_topic(candidates, checked):
        """After a refusal, the one subject the question named (so the page shows it), else None (the page keeps its
        topic), as the rules do for unsupported questions."""
        named = {c["name"] for c in candidates if c["source"] == "mention"}
        if len(named) != 1:
            return None
        name = named.pop()
        types = {c["type"] for c in candidates if c["name"] == name}
        types &= {c["type"] for _, c in checked if c["name"] == name} or types
        return {"name": name, "type": types.pop()} if len(types) == 1 else None

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
        keywords = self.keyword_words()
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
