"""Measure how many of our disease names also appear in MedlinePlus and the Disease Ontology (D-011 pilot).

Measurement only: nothing here is used at runtime, shipped or released. It counts lexical overlap between the 658
diseases in api/dictionary/entities.json and two public sources; it does not show that a matched name is the same
condition, that the source could answer our questions, or that either source is clinically reviewed (A-08).

    python scripts/dataset_pilot.py            # download (cached in pilot-data/) and measure
    python scripts/dataset_pilot.py --offline  # reuse the cached downloads

Writes the aggregate report to docs/pilot/DATASET-PILOT.md and the per-disease mappings to pilot-data/ (git-ignored,
kept local by the owner's choice). Any download or parsing failure stops the run: it is never reported as zero coverage.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.parsers import expat

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "api" / "dictionary" / "entities.json"
DATA = ROOT / "pilot-data"
REPORT = ROOT / "docs" / "pilot" / "DATASET-PILOT.md"

MEDLINEPLUS_INDEX = "https://medlineplus.gov/xml.html"
MEDLINEPLUS_FILE = re.compile(r"https://medlineplus\.gov/xml/mplus_topics_(\d{4}-\d{2}-\d{2})\.xml")
DOID_URL = "https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/releases/doid.obo"
MAX_BYTES = 100 * 1024 * 1024
TIMEOUT_SECONDS = 60
MIN_EXPAT = (2, 7, 2)  # Python's XML security notes warn about older Expat releases


class PilotError(Exception):
    """The measurement cannot be trusted; the message says why."""


# Downloads: an allow-list checked before every request, and no redirects at all.

def allowed(url):
    return url in (MEDLINEPLUS_INDEX, DOID_URL) or MEDLINEPLUS_FILE.fullmatch(url) is not None


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PilotError(f"{req.full_url} redirected (HTTP {code}); redirects are not followed")


OPENER = urllib.request.build_opener(NoRedirects)


def fetch(url, opener=None):
    if not allowed(url):
        raise PilotError(f"{url} is not an allowed source")
    request = urllib.request.Request(url, headers={"User-Agent": "Medical-ChatBot dataset pilot"})
    with (opener or OPENER).open(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise PilotError(f"{url} returned HTTP {response.status}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise PilotError(f"{url} is larger than {MAX_BYTES} bytes")
    if not data:
        raise PilotError(f"{url} was empty")
    return data


def cached(url, name, offline, fetcher=fetch):
    """The file's bytes, downloaded once; the cache is written only after a complete download."""
    path = DATA / name
    if path.exists():
        return path.read_bytes()
    if offline:
        raise PilotError(f"{name} is not cached; run without --offline first")
    data = fetcher(url)
    DATA.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(data)
    os.replace(partial, path)
    return data


def newest_medlineplus(index_html):
    """The newest dated health-topics XML linked from MedlinePlus's XML page."""
    dated = {}
    for href in re.findall(r'href="([^"]*mplus_topics_\d{4}-\d{2}-\d{2}\.xml)"', index_html):
        url = urllib.request.urljoin(MEDLINEPLUS_INDEX, href)
        match = MEDLINEPLUS_FILE.fullmatch(url)
        if match:
            dated[match.group(1)] = url
    if not dated:
        raise PilotError("No health-topics XML found on the MedlinePlus XML page")
    return dated[max(dated)]


# Parsing.

def normalise(name):
    """NFKC, casefolded, whitespace collapsed. Punctuation and plurals are kept: they can tell conditions apart."""
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def parse_medlineplus(data):
    """English health topics as {"id", "url", "names": [title, also-called...]}, parsed as a stream."""
    if expat.version_info < MIN_EXPAT:
        raise PilotError(f"Expat {'.'.join(map(str, expat.version_info))} is older than {'.'.join(map(str, MIN_EXPAT))}")
    parser = expat.ParserCreate()
    # No external DTD or parameter entities are ever loaded, and any entity declaration stops the parse.
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def refuse_entity(*args):
        raise PilotError("The XML declares entities, which this pilot does not accept")

    parser.EntityDeclHandler = refuse_entity
    topics, state = [], {"topic": None, "text": None, "total": 0}

    def start(tag, attrs):
        if tag == "health-topic":
            state["total"] += 1
            english = attrs.get("language") == "English" and attrs.get("title")
            state["topic"] = {"id": attrs.get("id"), "url": attrs.get("url"), "names": [attrs["title"]]} if english else None
        elif tag == "also-called" and state["topic"] is not None:
            state["text"] = []

    def end(tag):
        if tag == "also-called" and state["text"] is not None:
            name = "".join(state["text"]).strip()
            if name:
                state["topic"]["names"].append(name)
            state["text"] = None
        elif tag == "health-topic" and state["topic"] is not None:
            topics.append(state["topic"])
            state["topic"] = None

    def text(chunk):
        if state["text"] is not None:
            state["text"].append(chunk)

    parser.StartElementHandler, parser.EndElementHandler, parser.CharacterDataHandler = start, end, text
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise PilotError(f"MedlinePlus XML is malformed ({error})") from None
    if not topics:
        raise PilotError("MedlinePlus XML has no English health topics")
    return topics, state["total"]


OBO_SYNONYM = re.compile(r'synonym: "((?:[^"\\]|\\.)*)" (EXACT|BROAD|NARROW|RELATED)\b')


def unescape_obo(text):
    return re.sub(r"\\(.)", r"\1", text)


def parse_doid(text):
    """Non-obsolete DOID terms as {"id", "names": [name, EXACT synonyms...]}, plus the file's data-version."""
    version = re.search(r"^data-version: (.+)$", text, re.MULTILINE)
    terms, total = [], 0
    for stanza in re.split(r"\n(?=\[)", text):
        if not stanza.startswith("[Term]"):
            continue
        total += 1
        lines = stanza.splitlines()
        term_id = next((line[4:].strip() for line in lines if line.startswith("id: ")), "")
        name = next((line[6:].strip() for line in lines if line.startswith("name: ")), "")
        if not term_id.startswith("DOID:") or not name or "is_obsolete: true" in lines:
            continue
        names = [name]
        for line in lines:
            match = OBO_SYNONYM.match(line)
            if match and match.group(2) == "EXACT":
                names.append(unescape_obo(match.group(1)))
        terms.append({"id": term_id, "names": names})
    if not terms:
        raise PilotError("The Disease Ontology file has no usable terms")
    return terms, total, version.group(1).strip() if version else "unknown"


# Measuring.

def name_index(entries, key):
    index = {}
    for entry in entries:
        for name in entry["names"]:
            index.setdefault(normalise(name), set()).add(entry[key])
    return index


def measure(diseases, medlineplus, doid):
    """Per disease, the matching MedlinePlus topic URLs and DOID IDs; totals count each disease once per source."""
    mp_index, do_index = name_index(medlineplus, "url"), name_index(doid, "id")
    mappings, counts = [], dict.fromkeys(("medlineplus", "doid", "either", "both", "neither",
                                          "medlineplus_ambiguous", "doid_ambiguous"), 0)
    for disease in diseases:
        key = normalise(disease)
        mp, do = sorted(mp_index.get(key, ())), sorted(do_index.get(key, ()))
        mappings.append({"disease": disease, "medlineplus": mp, "doid": do})
        counts["medlineplus"] += bool(mp)
        counts["doid"] += bool(do)
        counts["either"] += bool(mp or do)
        counts["both"] += bool(mp and do)
        counts["neither"] += not (mp or do)
        counts["medlineplus_ambiguous"] += len(mp) > 1
        counts["doid_ambiguous"] += len(do) > 1
    return mappings, counts


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def report(result):
    n = result["diseases"]
    pct = lambda k: f"{result['counts'][k]} ({100 * result['counts'][k] / n:.1f}%)"  # noqa: E731
    s = result["sources"]
    return f"""# Dataset pilot: name overlap

Measured {result['measured_at']} at commit `{result['commit'][:12]}` by `scripts/dataset_pilot.py` (D-011, measurement only).

**What this shows.** How many of our {n} disease names (`api/dictionary/entities.json`, SHA-256 `{result['dictionary_sha256'][:16]}…`, CSV source `{result['source_sha256'][:16]}…`) appear, after NFKC, casefolding and collapsing whitespace, as a MedlinePlus English health-topic title or "also called" name, or as a Disease Ontology term name or EXACT synonym. Punctuation and plurals are kept and nothing fuzzy is counted.

**What it does not show.** A matched name is lexical overlap, not proof of the same condition. Neither source is shown to answer our seven question types, and MedlinePlus summaries are not established as clinically reviewed (A-08). "Unmatched" means this method found no match. The CSV's own rights (A-01) are unaffected.

| Source | Diseases matched |
|---|---|
| MedlinePlus | {pct('medlineplus')} |
| Disease Ontology | {pct('doid')} |
| Either | {pct('either')} |
| Both | {pct('both')} |
| Neither | {pct('neither')} |
| Matched more than one MedlinePlus topic | {result['counts']['medlineplus_ambiguous']} |
| Matched more than one DOID term | {result['counts']['doid_ambiguous']} |

**Sources.**

- MedlinePlus: `{s['medlineplus']['url']}`, SHA-256 `{s['medlineplus']['sha256']}`, {s['medlineplus']['english_topics']} English of {s['medlineplus']['topics']} health topics. Topic data from MedlinePlus.gov; MedlinePlus invites reuse of its XML with attribution and states that health-topic summaries are public domain, while other material it links may be copyrighted.
- Disease Ontology: `{s['doid']['url']}` ({s['doid']['version']}), SHA-256 `{s['doid']['sha256']}`, {s['doid']['usable_terms']} usable of {s['doid']['terms']} terms; licensed CC0 1.0.

The per-disease mappings are in `pilot-data/mappings.json`, which is not committed.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="use only cached downloads")
    args = parser.parse_args(argv)
    try:
        dictionary_bytes = ENTITIES.read_bytes()
        dictionary = json.loads(dictionary_bytes)
        diseases = dictionary["diseases"]
        index_html = cached(MEDLINEPLUS_INDEX, "xml.html", args.offline).decode("utf-8", "replace")
        mp_url = newest_medlineplus(index_html)
        mp_bytes = cached(mp_url, mp_url.rsplit("/", 1)[1], args.offline)
        do_bytes = cached(DOID_URL, "doid.obo", args.offline)
        medlineplus, mp_total = parse_medlineplus(mp_bytes)
        doid, do_total, do_version = parse_doid(do_bytes.decode("utf-8"))
    except (OSError, ValueError, KeyError, PilotError) as error:
        print(f"Dataset pilot failed: {error}", file=sys.stderr)
        return 1
    mappings, counts = measure(diseases, medlineplus, doid)
    result = {
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit(),
        "diseases": len(diseases), "dictionary_sha256": sha256(dictionary_bytes), "source_sha256": dictionary.get("source_sha256", ""),
        "counts": counts,
        "sources": {"medlineplus": {"url": mp_url, "sha256": sha256(mp_bytes), "topics": mp_total, "english_topics": len(medlineplus)},
                    "doid": {"url": DOID_URL, "sha256": sha256(do_bytes), "version": do_version, "terms": do_total, "usable_terms": len(doid)}},
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "mappings.json").write_text(json.dumps({**result, "mappings": mappings}, indent=1), encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(result), encoding="utf-8")
    print(f"Either source: {counts['either']} of {len(diseases)} diseases; report in {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
