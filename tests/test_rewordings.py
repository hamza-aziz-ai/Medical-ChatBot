"""Approved rewordings served only on an exact match (D-029); everything else shows the original."""
import json

import answer_searcher as a
import text_format as tf

VALUE = "daily prevention: 1. avoid allergens. 2, no pets indoors."
REWORDED = [{"heading": "Daily prevention", "paragraph": None, "items": ["Stay away from things you are allergic to.", "Do not keep pets indoors."]}]


def entry(values=(VALUE,), sections=REWORDED, **changes):
    item = {"subject": "asthma", "intent": "disease_prevention", "status": "approved",
            "input_sha256": a.digest(a.canonical_input("asthma", "disease_prevention", list(values))),
            "format_identity": tf.FORMAT_IDENTITY, "sections": sections, "output_sha256": a.sections_digest(sections)}
    item.update(changes)
    return item


def searcher_with(tmp_path, *entries):
    path = tmp_path / "rewordings.json"
    path.write_text(json.dumps({"entries": list(entries)}), encoding="utf-8")
    searcher = a.AnswerSearcher(driver=object())
    searcher.rewordings = a.load_rewordings(path)
    return searcher


def answer_for(searcher, value=VALUE):
    [result] = searcher.structure("disease_prevention", [{"subject": "asthma", "value": value}])
    return result


def test_the_shipped_store_holds_only_owner_approved_entries_that_all_load():
    # D-029: the owner approved all ten pilot fields on 2026-10-28, overriding the failed checks of eight; each override
    # names the checks it overruled. Nothing outside the pilot is served.
    shipped = json.loads(a.REWORDINGS_PATH.read_text(encoding="utf-8"))["entries"]
    assert len(shipped) == 10 and all(e["status"] == "approved" for e in shipped)
    overridden = {(e["subject"], e["intent"]) for e in shipped if "override" in e}
    assert len(overridden) == 8 and all(e["checks_overridden"] for e in shipped if "override" in e)
    assert {(e["subject"], e["intent"]) for e in shipped} - overridden == {("migraine", "disease_description"), ("pertussis", "disease_prevention")}
    assert set(a.load_rewordings()) == {(e["subject"], e["intent"]) for e in shipped}  # none dropped as invalid
    assert "reworded" not in answer_for(a.AnswerSearcher(driver=object()))              # different input: original


def test_an_approved_exact_match_is_served_beside_the_untouched_original(tmp_path):
    result = answer_for(searcher_with(tmp_path, entry()))
    assert result["reworded"] is True and result["reworded_sections"] == REWORDED
    assert result["sections"][0]["items"] == ["Avoid allergens.", "No pets indoors."]
    assert result["text"].startswith("Precautions for asthma include: daily prevention: 1.")


def test_a_changed_input_is_not_served(tmp_path):
    assert "reworded" not in answer_for(searcher_with(tmp_path, entry()), value=VALUE.replace("pets", "cats"))


def test_entries_that_are_not_exactly_approved_are_skipped_at_load(tmp_path):
    tampered = entry()
    tampered["sections"] = [{"heading": "Daily prevention", "paragraph": None, "items": ["Keep pets indoors.", "x"]}]
    bad = [tampered,                                           # edited after approval: output hash no longer matches
           entry(format_identity="v1:" + "0" * 64),           # made with another formatter
           entry(status="candidate"),                         # never approved
           entry(intent="disease_symptom"),                   # not a prose answer
           entry(sections=[{"heading": None, "paragraph": "", "items": []}])]
    for item in bad:
        assert searcher_with(tmp_path, item).rewordings == {}


def test_a_rewording_with_other_headings_or_segments_is_not_served(tmp_path):
    other = [{"heading": "Something else", "paragraph": None, "items": ["A.", "B."]}]
    assert "reworded" not in answer_for(searcher_with(tmp_path, entry(sections=other)))


def test_a_malformed_or_missing_store_means_no_rewordings(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert a.load_rewordings(broken) == {} and a.load_rewordings(tmp_path / "missing.json") == {}


def test_plain_text_becomes_one_paragraph_segment_and_lists_keep_their_sections():
    assert tf.prose_segments(["dust and cold air."]) == [{"heading": None, "paragraph": "Dust and cold air.", "items": []}]
    assert tf.prose_segments([VALUE])[0]["items"] == ["Avoid allergens.", "No pets indoors."]
    assert tf.FORMAT_IDENTITY.startswith(f"v{tf.SCHEMA_VERSION}:") and len(tf.FORMAT_IDENTITY) == 67
