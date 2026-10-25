import logging

from answer_searcher import AnswerSearcher
from question_classifier import QuestionClassifier
from question_parser import QuestionParser

logger = logging.getLogger(__name__)

ABSTENTION = (
    "I cannot answer this question from the available medical knowledge graph. "
    "Please consult a qualified medical professional."
)

UNSUPPORTED_INTENTS = frozenset({
    "disease_last_time",
    "disease_cure_probability",
    "disease_easy_get",
})


class ChatBotGraph:
    def __init__(self):
        self.classifier = QuestionClassifier()
        self.parser = QuestionParser()
        self.searcher = AnswerSearcher()
        logger.info("Chatbot ready: %d disease, %d symptom and %d department terms loaded",
                    len(self.classifier.disease_words), len(self.classifier.symptom_words), len(self.classifier.department_words))

    def chat_main(self, sent):
        # Log intent names and counts only: entity names come from the user's question.
        result_classify = self.classifier.classify(sent)

        if not result_classify:
            logger.info("Abstained: no known entity in the question")
            return ABSTENTION

        intents = result_classify["question_types"]
        logger.debug("Classified %d entit(ies) with intents %s", len(result_classify["arguments"]), intents)
        if UNSUPPORTED_INTENTS.intersection(intents):
            logger.info("Abstained: unsupported intent %s", sorted(UNSUPPORTED_INTENTS.intersection(intents)))
            return ABSTENTION

        result_sql = self.parser.parser_main(result_classify)
        final_answers = self.searcher.search_main(result_sql)
        if not final_answers:
            logger.info("Abstained: the graph had no answer for intents %s", intents)
            return ABSTENTION
        logger.info("Answered with %d sentence(s) for intents %s", len(final_answers), intents)
        return "\n".join(final_answers)
