from question_classifier import QuestionClassifier


def test_loads_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert QuestionClassifier().disease_words


def test_terms_only_match_whole_words():
    classifier = QuestionClassifier()
    assert classifier.check_medical("what is the treatment in spain") == {}
    assert "cold" not in classifier.check_medical("why do parents scold children")


def test_nested_match_is_suppressed_but_separate_mentions_are_kept():
    classifier = QuestionClassifier()
    assert list(classifier.check_medical("symptoms of allergic asthma")) == ["allergic asthma"]
    assert list(classifier.check_medical("symptoms of asthma and allergic asthma")) == ["asthma", "allergic asthma"]


def test_artefact_terms_are_not_loaded():
    classifier = QuestionClassifier()
    assert "..." not in classifier.symptom_words
    assert "living" not in classifier.symptom_words


def test_unsupported_intent_is_still_detected():
    assert "disease_last_time" in QuestionClassifier().classify("how long does asthma last")["question_types"]


def test_intent_keywords_match_whole_words_only():
    check = QuestionClassifier.check_words
    for word, sentence in [("day", "today"), ("time", "sometimes"), ("who", "whole"), ("cause", "because"), ("infect", "disinfect")]:
        assert not check([word], f"it happened {sentence}")
    assert check(["how can i not"], "How  can I   NOT get asthma")


def test_common_question_forms_keep_their_intent():
    classifier = QuestionClassifier()
    assert "disease_cause" in classifier.classify("what causes asthma")["question_types"]
    assert "disease_symptom" in classifier.classify("symptoms of asthma")["question_types"]
    assert "disease_cure_way" in classifier.classify("how is asthma treated")["question_types"]
    assert "disease_prevention" in classifier.classify("how can i not get asthma")["question_types"]
    assert "disease_easy_get" not in classifier.classify("is asthma a whole body disease")["question_types"]


def test_unused_keyword_lists_are_gone():
    classifier = QuestionClassifier()
    assert not hasattr(classifier, "belong_question_words")
    assert not hasattr(classifier, "cure_question_words")
