"""Sections and numbered points in long graph text (D-028): structure only, never different words."""
import csv
import re
from pathlib import Path

import answer_searcher
import text_format as tf

CSV = Path(__file__).resolve().parents[1] / "api" / "data" / "medical.csv"


def letters(text):
    return re.sub(r"[^a-z]", "", text.lower())


def flat(sections):
    return " ".join(" ".join(filter(None, [s["paragraph"], s["heading"]] + s["items"])) for s in sections)


def test_two_labelled_lists_become_two_sections():
    text = ("daily prevention: 1. avoid allergens. keep windows open. 2, no pets indoors. "
            "health education: 1. psychological guidance: stay calm. 2, diet guidance: avoid shrimp.")
    assert tf.sections(text) == [
        {"heading": "Daily prevention", "paragraph": None, "items": ["Avoid allergens. keep windows open.", "No pets indoors."]},
        {"heading": "Health education", "paragraph": None, "items": ["Psychological guidance: stay calm.", "Diet guidance: avoid shrimp."]},
    ]


def test_an_introduction_stays_a_paragraph_and_parenthesised_points_are_points():
    text = "most cases are mild and the following points matter in daily life: (1) diet first. (2) rest well."
    sections = tf.sections(text)
    assert sections[0]["items"] == ["Diet first.", "Rest well."]
    assert sections[0]["heading"] is None or len(sections[0]["heading"]) <= tf.MAX_HEADING


def test_text_without_a_clear_numbered_run_is_left_alone():
    assert tf.sections("take 1.5 mg twice a day; it is not a cure.") is None   # a decimal is not a marker
    assert tf.sections("only one point: 1. rest.") is None                     # one point is not a list
    assert tf.sections("1. rest. 3. drink water.") is None                     # numbers must count up from 1


def test_a_new_list_is_never_read_as_the_continuation_of_the_last():
    text = "a: 1. x. 2, y. b: 1. p. 2, q. 3, r."
    assert [len(s["items"]) for s in tf.sections(text)] == [2, 3]


def test_every_letter_of_every_stored_field_survives_in_order():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    structured = 0
    for row in rows:
        for field in ("Description", "Prevention", "Causes"):
            found = tf.sections(row[field])
            if found:
                structured += 1
                assert letters(flat(found)) == letters(row[field]), (row["Name"], field)
    assert structured > 400


def test_text_answers_carry_sections_only_when_the_text_has_them():
    searcher = answer_searcher.AnswerSearcher(driver=object())
    rows = [{"subject": "asthma", "value": "daily prevention: 1. avoid allergens. 2, no pets indoors."}]
    [entry] = searcher.structure("disease_prevention", rows)
    assert entry["lead"] == "Precautions for asthma include:" and entry["sections"][0]["items"] == ["Avoid allergens.", "No pets indoors."]
    assert entry["text"].startswith("Precautions for asthma include: daily prevention: 1.")   # the plain message is unchanged
    [plain] = searcher.structure("disease_cause", [{"subject": "asthma", "value": "dust and cold air."}])
    assert "sections" not in plain
