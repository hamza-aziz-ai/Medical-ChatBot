"""The dataset pilot (D-011), offline: parsing, matching, safety and failure handling. CI never downloads."""
import email.message
import importlib.util
import io
import urllib.request
import urllib.response
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("dataset_pilot", Path(__file__).resolve().parents[1] / "scripts" / "dataset_pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

MEDLINEPLUS = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE health-topics PUBLIC "-//NLM//DTD health-topics //EN" "https://medlineplus.gov/xml/mplus_topics.dtd">
<health-topics total="3">
<health-topic title="Asthma" url="https://medlineplus.gov/asthma.html" id="1" language="English">
<also-called>Bronchial asthma</also-called>
<full-summary>&lt;p&gt;text&lt;/p&gt;</full-summary>
</health-topic>
<health-topic title="Whooping Cough" url="https://medlineplus.gov/whoopingcough.html" id="2" language="English">
<also-called>Pertussis</also-called>
</health-topic>
<health-topic title="Asma" url="https://medlineplus.gov/spanish/asthma.html" id="3" language="Spanish">
<also-called>Gout</also-called>
</health-topic>
</health-topics>
"""

DOID = """format-version: 1.2
data-version: releases/2026-09-30/doid.obo

[Term]
id: DOID:2841
name: asthma
synonym: "bronchial \\"asthma\\"" EXACT []

[Term]
id: DOID:13189
name: gout
synonym: "gouty arthritis" RELATED []

[Term]
id: DOID:9999
name: anemia
is_obsolete: true

[Term]
id: DOID:1000
name: pertussis
synonym: "Asthma" EXACT []

[Typedef]
id: part_of
name: part of
"""


def test_medlineplus_keeps_english_topics_with_their_also_called_names():
    topics, total = pilot.parse_medlineplus(MEDLINEPLUS)
    assert total == 3
    assert [t["names"] for t in topics] == [["Asthma", "Bronchial asthma"], ["Whooping Cough", "Pertussis"]]
    assert topics[0]["url"] == "https://medlineplus.gov/asthma.html"


def test_entity_declarations_and_old_expat_are_refused(monkeypatch):
    with pytest.raises(pilot.PilotError, match="declares entities"):
        pilot.parse_medlineplus(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    monkeypatch.setattr(pilot.expat, "version_info", (2, 6, 0))
    with pytest.raises(pilot.PilotError, match="older than"):
        pilot.parse_medlineplus(MEDLINEPLUS)


def test_malformed_or_empty_sources_fail_the_run():
    with pytest.raises(pilot.PilotError, match="malformed"):
        pilot.parse_medlineplus(b"<health-topics><health-topic")
    with pytest.raises(pilot.PilotError, match="no English"):
        pilot.parse_medlineplus(b'<health-topics><health-topic title="Asma" language="Spanish"/></health-topics>')
    with pytest.raises(pilot.PilotError, match="no usable terms"):
        pilot.parse_doid("format-version: 1.2\n")


def test_doid_keeps_live_terms_and_exact_synonyms_only():
    terms, total, version = pilot.parse_doid(DOID)
    assert version == "releases/2026-09-30/doid.obo" and total == 4
    names = {t["id"]: t["names"] for t in terms}
    assert names["DOID:2841"] == ["asthma", 'bronchial "asthma"']  # escaped quotes unescaped
    assert names["DOID:13189"] == ["gout"]                         # RELATED synonym ignored
    assert "DOID:9999" not in names                                # obsolete term ignored


def test_matching_is_strict_counts_each_disease_once_and_flags_ambiguity():
    medlineplus, _ = pilot.parse_medlineplus(MEDLINEPLUS)
    doid, _, _ = pilot.parse_doid(DOID)
    diseases = ["asthma", "Pertussis", "gout", "gouts", "gout!", "anemia", "unknown"]
    mappings, counts = pilot.measure(diseases, medlineplus, doid)
    by_name = {m["disease"]: m for m in mappings}
    assert by_name["asthma"]["doid"] == ["DOID:1000", "DOID:2841"]   # two terms: ambiguous, still one disease
    assert by_name["Pertussis"]["medlineplus"] == ["https://medlineplus.gov/whoopingcough.html"]
    assert not by_name["gouts"]["doid"] and not by_name["gout!"]["doid"]  # no plural or punctuation folding
    assert counts == {"medlineplus": 2, "doid": 3, "either": 3, "both": 2, "neither": 4,
                      "medlineplus_ambiguous": 0, "doid_ambiguous": 1}


def test_normalisation_folds_width_case_and_spaces_only():
    assert pilot.normalise("  Ｃrohn  Disease ") == "crohn disease"
    assert pilot.normalise("HIV+") != pilot.normalise("HIV-")


def test_only_allowed_urls_are_requested_and_redirects_are_refused():
    requests = []

    class Recorder(urllib.request.BaseHandler):
        handler_order = 100  # before the real HTTPS handler, so the test never touches the network

        def https_open(self, req):
            requests.append(req.full_url)
            headers = email.message.Message()
            headers["Location"] = "https://example.com/x"
            response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            response.msg = "Found"
            return response

    opener = urllib.request.build_opener(pilot.NoRedirects, Recorder)
    with pytest.raises(pilot.PilotError, match="not an allowed source"):
        pilot.fetch("https://example.com/data.xml", opener)
    assert requests == []
    with pytest.raises(pilot.PilotError, match="redirected"):
        pilot.fetch(pilot.DOID_URL, opener)
    assert requests == [pilot.DOID_URL]  # the redirect target was never requested


def test_the_newest_dated_file_is_chosen():
    html = '<a href="xml/mplus_topics_2026-10-23.xml">x</a> <a href="https://medlineplus.gov/xml/mplus_topics_2026-10-24.xml">y</a>'
    assert pilot.newest_medlineplus(html) == "https://medlineplus.gov/xml/mplus_topics_2026-10-24.xml"
    with pytest.raises(pilot.PilotError):
        pilot.newest_medlineplus("<html></html>")


def test_the_cache_is_written_only_after_a_complete_download(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "DATA", tmp_path)

    def failing(url):
        raise pilot.PilotError("connection reset")

    with pytest.raises(pilot.PilotError):
        pilot.cached(pilot.DOID_URL, "doid.obo", offline=False, fetcher=failing)
    assert list(tmp_path.iterdir()) == []
    assert pilot.cached(pilot.DOID_URL, "doid.obo", offline=False, fetcher=lambda url: b"data") == b"data"
    assert pilot.cached(pilot.DOID_URL, "doid.obo", offline=True, fetcher=failing) == b"data"
    with pytest.raises(pilot.PilotError, match="not cached"):
        pilot.cached(pilot.DOID_URL, "other.obo", offline=True)
