from answer_searcher import AnswerSearcher
from conftest import FakeDriver
from question_parser import TEMPLATES, QuestionParser


def test_entity_names_are_parameters_not_query_text():
    name = "crohn's disease"
    for question_type in TEMPLATES:
        for query, params in QuestionParser.sql_transfer(question_type, [name]):
            assert name not in query
            assert params == {"name": name, "limit": 20}
            assert "$name" in query


def test_parser_routes_symptom_questions_by_symptom():
    classification = {
        "arguments": {"asthma": ["disease"], "wheeze": ["symptom"]},
        "question_types": ["symptom_disease"],
    }
    [group] = QuestionParser().parser_main(classification)
    assert [params["name"] for _, params in group["sql"]] == ["wheeze"]


def test_answers_are_grouped_per_subject_and_not_diagnostic():
    searcher = AnswerSearcher(driver=FakeDriver())
    rows = [
        {"subject": "wheeze", "value": "asthma"},
        {"subject": "cough", "value": "bronchitis"},
        {"subject": "wheeze", "value": "bronchitis"},
    ]
    assert searcher.answer_prettify("symptom_disease", rows) == [
        "Diseases recorded as associated with symptom cough: bronchitis. This is not a diagnosis.",
        "Diseases recorded as associated with symptom wheeze: asthma, bronchitis. This is not a diagnosis.",
    ]


def test_accompanying_conditions_label():
    searcher = AnswerSearcher(driver=FakeDriver())
    rows = [{"subject": "asthma", "value": "rhinitis"}]
    assert searcher.answer_prettify("disease_accompany", rows) == ["Accompanying conditions recorded for asthma: rhinitis"]


def test_missing_treatment_abstains_while_description_answers():
    searcher = AnswerSearcher(driver=FakeDriver())
    assert searcher.answer_prettify("disease_cure_way", [{"subject": "asthma", "value": None}]) == []
    assert searcher.answer_prettify("disease_cure_way", [{"subject": "asthma", "value": []}]) == []
    assert searcher.answer_prettify("disease_description", [{"subject": "asthma", "value": "A lung disease."}]) == [
        "asthma, familiar with: A lung disease."
    ]


def test_artefact_terms_are_not_served():
    searcher = AnswerSearcher(driver=FakeDriver())
    rows = [{"subject": "x", "value": v} for v in ("living", "...", "", "cough")]
    assert searcher.answer_prettify("disease_symptom", rows) == ["The symptoms of x include: cough"]


def test_search_main_passes_parameters_to_the_driver():
    driver = FakeDriver(rows=[{"subject": "asthma", "value": "dust"}])
    searcher = AnswerSearcher(driver=driver)
    sqls = [{"question_type": "disease_cause", "sql": QuestionParser.sql_transfer("disease_cause", ["asthma"])}]
    assert searcher.search_main(sqls) == ["The possible causes of asthma are: dust"]
    [(query, params)] = driver.calls
    assert params["name"] == "asthma"


def test_treatment_query_limits_list_elements():
    [(query, params)] = QuestionParser.sql_transfer("disease_cure_way", ["asthma"])
    assert "UNWIND m.cure_way AS value" in query
    assert "ORDER BY subject, value LIMIT $limit" in query
    assert params["limit"] == 20


def test_formatting_is_deterministic_and_capped():
    import random

    searcher = AnswerSearcher(driver=FakeDriver())
    values = [f"treatment {i:02d}" for i in range(30)] * 2
    random.Random(7).shuffle(values)
    [answer] = searcher.answer_prettify("disease_cure_way", [{"subject": "asthma", "value": v} for v in values])
    listed = answer.split(": ", 1)[1].split("; ")
    assert listed == [f"treatment {i:02d}" for i in range(20)]
