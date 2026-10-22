import json

from keras.models import model_from_json
from keras.preprocessing.text import text_to_word_sequence
from keras.utils import pad_sequences

from answer_searcher import *
from question_classifier import *
from question_parser import *


# ============================ SIAMESE MODEL ============================
def load_siamese_model():
    json_file = open("./models/model1.json")
    loaded_model_json = json_file.read()
    json_file.close()

    # load model
    model = model_from_json(loaded_model_json)

    # load weights
    model.load_weights("./models/question_pairs_weights_type1_final_new.h5")

    return model


def convert_text_to_index_array(text, dictionary):
    words = text_to_word_sequence(text)
    word_indices = []
    for word in words:
        if word in dictionary:
            word_indices.append(dictionary[word])
        else:
            print(f"'{word}' not in training corpus; ignoring.")

    return word_indices


def find_if_duplicate_questions(question_1, question_2):
    with open("./models/dictionary.json", 'r') as dictionary_file:
        dictionary = json.load(dictionary_file)

    max_sequence_length = 130
    question1_word_sequence = convert_text_to_index_array(question_1, dictionary)
    question1_word_sequence = [question1_word_sequence]
    question2_word_sequence = convert_text_to_index_array(question_2, dictionary)
    question2_word_sequence = [question2_word_sequence]

    question1_data = pad_sequences(question1_word_sequence, maxlen=max_sequence_length)
    question2_data = pad_sequences(question2_word_sequence, maxlen=max_sequence_length)

    model = load_siamese_model()

    prediction = model.predict([question1_data, question2_data])

    return prediction
# ============================ END SIAMESE MODEL ============================


def find_similar_question(sent):
    with open("./data/questions.json", encoding="utf-8", errors="ignore") as file:
        data_questions = json.load(file)
        scores = []

        for i in range(10):
            question = data_questions[i]["question"]
            score = find_if_duplicate_questions(sent, question)
            scores.append(score)

        minimum = 9999

        for i in range(len(scores)):
            if scores[i] < minimum:
                minimum = i

        question = data_questions[minimum]["question"]
        answer = data_questions[minimum]["answer"]

        return question, answer


class ChatBotGraph:
    def __init__(self):
        self.classifier = QuestionClassifier()
        self.parser = QuestionParser()
        self.searcher = AnswerSearcher()

    def chat_main(self, sent):
        result_classify = self.classifier.classify(sent)

        if not result_classify:
            question, stage2_answer = find_similar_question(sent)
            return f"I don't know if I fully understand the question, but here's what I found: \n {stage2_answer}"

        result_sql = self.parser.parser_main(result_classify)

        final_answers = self.searcher.search_main(result_sql)

        if not final_answers:
            # Perform Stage 2: Using datasets by checking question similarity in a loop and extracting answer from the least score
            question, stage2_answer = find_similar_question(sent)
            return f"I don't know if I fully understand the question, but here's what I found: \n {stage2_answer}"
        else:
            return '\n'.join(final_answers)
