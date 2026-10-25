from answer_searcher import AnswerSearcher
from question_classifier import QuestionClassifier
from question_parser import QuestionParser

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

    def chat_main(self, sent):
        result_classify = self.classifier.classify(sent)

        if not result_classify or UNSUPPORTED_INTENTS.intersection(
            result_classify["question_types"]
        ):
            return ABSTENTION

        result_sql = self.parser.parser_main(result_classify)
        final_answers = self.searcher.search_main(result_sql)
        return "\n".join(final_answers) if final_answers else ABSTENTION
