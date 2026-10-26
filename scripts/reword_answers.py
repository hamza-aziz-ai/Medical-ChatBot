"""Offline rewording of prose answers for owner review (D-029). Never imported by the API; never run in CI.

    python scripts/reword_answers.py --inventory                 # sizes of the pilot fields; no model calls
    python scripts/reword_answers.py --challenge                 # measure the checks on reviewed broken rewrites
    python scripts/reword_answers.py --generate                  # reword the pilot fields into local candidates
    python scripts/reword_answers.py --review                    # write the local side-by-side review page
    python scripts/reword_answers.py --approve decisions.json    # publish only owner-approved, unchanged candidates

Candidates, diagnostics and the review page stay in git-ignored pilot-data/rewordings/. Only --approve writes to
api/dictionary/rewordings.json, and only entries whose input, output and formatter identity still match what the
owner reviewed. The checks below are filters, not proof; the verifier is the same model as the writer (correlated).
"""
import argparse
import html
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import answer_searcher  # noqa: E402
import build_medicalgraph as builder  # noqa: E402
import text_format  # noqa: E402
import understanding  # noqa: E402
from question_classifier import QuestionClassifier  # noqa: E402

OUT = ROOT / "pilot-data" / "rewordings"
CHALLENGES = ROOT / "eval" / "rewording-challenges.jsonl"
REPORT = ROOT / "docs" / "pilot" / "REWORDING.md"
FIELDS = {"disease_description": "description", "disease_cause": "causes", "disease_prevention": "prevention"}
# Agreed with Codex from the inventory: moderate fields across the three prose intents. Recorded before generation.
PILOT = [("asthma", "disease_prevention"), ("asthma", "disease_cause"), ("migraine", "disease_description"),
         ("migraine", "disease_cause"), ("migraine", "disease_prevention"), ("gout", "disease_prevention"),
         ("obesity", "disease_prevention"), ("osteoarthritis", "disease_description"), ("osteoarthritis", "disease_cause"),
         ("pertussis", "disease_prevention")]
MAX_CHARS, MAX_SEGMENTS = 4000, 15
OFFLINE_TIMEOUT = 30.0

REWORD_PROMPT = """You rewrite one passage of a medical reference text so it reads clearly in plain English.

The user message is a JSON object: "field" is the whole text, for context only; "heading" may label the passage; "passage" is the ONLY text to rewrite.

Rules:
- Keep every fact, number, unit, dose, condition, cause, recommendation and negation exactly as stated. Do not change how certain a statement is.
- Add nothing: no new facts, advice, warnings or examples. Remove nothing.
- Keep it about the same length, as plain sentences without lists, numbering or markdown.
- If the passage is unclear, keep its meaning as written rather than guessing.

Reply with exactly one JSON object and nothing else: {"text": "<the rewritten passage>"}"""

VERIFY_PROMPT = """You check a rewrite of a medical reference text against the original. Judge only against the original; ignore whether the medicine is right.

The user message is a JSON object with "original" and "rewrite".

Reply with exactly one JSON object and nothing else:
{"adds": bool, "omits": bool, "contradicts": bool, "reverses_cause": bool, "changes_certainty": bool, "changes_quantity": bool}

Each is true if the rewrite: adds a fact the original does not state; leaves out a fact the original states; contradicts it; reverses a cause and its effect; makes a statement more or less certain (for example "may" becoming "will"); or changes a number, unit, dose or which thing a quantity belongs to."""

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
UNITS = {"mg", "g", "kg", "ml", "l", "%", "mmhg", "°c", "minutes", "minute", "hours", "hour", "days", "day", "weeks", "week",
         "months", "month", "years", "year", "times", "cm", "mm"}
NEGATIONS = {"not", "no", "never", "without", "avoid", "avoided", "avoiding", "nor", "none", "cannot", "neither",
             "don't", "doesn't", "didn't", "can't", "won't", "shouldn't", "mustn't", "isn't", "aren't", "never"}
VERIFY_FLAGS = ("adds", "omits", "contradicts", "reverses_cause", "changes_certainty", "changes_quantity")


class Calls:
    """Every cloud call is counted; the run stops before exceeding the cap it was given."""

    def __init__(self, cap):
        self.cap, self.made = cap, 0

    def chat(self, system, payload):
        if self.made >= self.cap:
            raise understanding.ModelError("call cap reached")
        self.made += 1
        content, _ = understanding.chat([{"role": "system", "content": system},
                                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                                        understanding.DEFAULT_URL, understanding.DEFAULT_MODEL, timeout=OFFLINE_TIMEOUT)
        return json.loads(content.strip())


def tokens(text):
    return re.findall(r"[a-z%°]+(?:'[a-z]+)?|\d+(?:[.,]\d+)?", text.lower())


def mechanical(source, rewrite, classifier):
    """Failures of the cheap filters for one passage; an empty list passes. Equal counts do not prove equal meaning."""
    failures = []
    if Counter(NUMBER.findall(source)) != Counter(NUMBER.findall(rewrite)):
        failures.append("numbers")
    if Counter(t for t in tokens(source) if t in UNITS) != Counter(t for t in tokens(rewrite) if t in UNITS):
        failures.append("units")
    if sum(t in NEGATIONS for t in tokens(source)) != sum(t in NEGATIONS for t in tokens(rewrite)):
        failures.append("negations")
    if set(classifier.check_medical(rewrite.lower())) - set(classifier.check_medical(source.lower())):
        failures.append("new_names")
    if not 0.5 <= len(rewrite) / max(1, len(source)) <= 1.6:
        failures.append("length")
    return failures


def verify(calls, original, rewrite):
    """The verifier's failures for a whole field; anything malformed, late or unclear fails."""
    try:
        reply = calls.chat(VERIFY_PROMPT, {"original": original, "rewrite": rewrite})
    except (understanding.ModelError, OSError, ValueError, KeyError, TypeError) as error:
        return [f"verifier_{type(error).__name__}"]
    if not isinstance(reply, dict) or set(reply) != set(VERIFY_FLAGS) or not all(isinstance(reply[f], bool) for f in VERIFY_FLAGS):
        return ["verifier_malformed"]
    return [flag for flag in VERIFY_FLAGS if reply[flag]]


def field_values(dataset):
    """{(subject, intent): values} exactly as the API serves them, built from the importer's own data, no database."""
    searcher = answer_searcher.AnswerSearcher(driver=object())
    rows = {row["name"]: row["properties"] for row in builder.graph_data(dataset)["diseases"]}
    values = {}
    for subject, intent in PILOT:
        grouped = searcher.group_values(intent, [{"subject": subject, "value": rows.get(subject, {}).get(FIELDS[intent])}])
        if grouped.get(subject):
            values[(subject, intent)] = grouped[subject]
    return values


def flat(segments):
    return "\n".join("\n".join(filter(None, [s["heading"], s["paragraph"]] + s["items"])) for s in segments)


def inventory(values):
    lines = []
    for (subject, intent), vals in values.items():
        segments = text_format.prose_segments(vals)
        units = sum(1 if s["paragraph"] else 0 for s in segments) + sum(len(s["items"]) for s in segments)
        chars = sum(len(v) for v in vals)
        ok = chars <= MAX_CHARS and units <= MAX_SEGMENTS
        lines.append(f"{subject} / {intent}: {chars} characters, {units} passages, {'in' if ok else 'out of'} bounds")
    return lines


def generate(values, calls, classifier):
    OUT.mkdir(parents=True, exist_ok=True)
    for (subject, intent), vals in values.items():
        segments = text_format.prose_segments(vals)
        field_text = flat(segments)
        if len(field_text) > MAX_CHARS or sum(bool(s["paragraph"]) + len(s["items"]) for s in segments) > MAX_SEGMENTS:
            continue
        identity = {"subject": subject, "intent": intent,
                    "input_sha256": answer_searcher.digest(answer_searcher.canonical_input(subject, intent, vals)),
                    "format_identity": text_format.FORMAT_IDENTITY,
                    "reword_prompt_sha256": answer_searcher.digest(REWORD_PROMPT),
                    "verify_prompt_sha256": answer_searcher.digest(VERIFY_PROMPT),
                    "model": understanding.DEFAULT_MODEL, "options": understanding.OPTIONS, "think": understanding.THINK}
        path = OUT / f"{subject.replace(' ', '_')}--{intent}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if all(old.get(k) == v for k, v in identity.items()):
                continue   # resume: same input, prompts and settings
        reworded, passage_checks = [], []
        try:
            for section in segments:
                new = {"heading": section["heading"], "paragraph": None, "items": []}
                passages = ([("paragraph", section["paragraph"])] if section["paragraph"] else []) + [("item", i) for i in section["items"]]
                for kind, passage in passages:
                    reply = calls.chat(REWORD_PROMPT, {"field": field_text, "heading": section["heading"], "passage": passage})
                    text = reply.get("text") if isinstance(reply, dict) else None
                    if not isinstance(text, str) or not text.strip():
                        raise understanding.ModelError("malformed rewording")
                    text = " ".join(text.split())
                    passage_checks.append({"source": passage, "rewrite": text, "failures": mechanical(passage, text, classifier)})
                    if kind == "paragraph":
                        new["paragraph"] = text
                    else:
                        new["items"].append(text)
                reworded.append(new)
        except (understanding.ModelError, OSError, ValueError, KeyError, TypeError) as error:
            print(f"{subject} / {intent}: stopped ({type(error).__name__}: {error})")
            continue
        field_failures = verify(calls, field_text, flat(reworded))
        candidate = {**identity, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                     "original_sections": segments, "sections": reworded,
                     "output_sha256": answer_searcher.sections_digest(reworded), "passages": passage_checks,
                     "field_failures": field_failures,
                     "checks_passed": not field_failures and not any(p["failures"] for p in passage_checks)}
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{subject} / {intent}: {'passed' if candidate['checks_passed'] else 'flagged'} ({calls.made} calls so far)")


def challenge(calls, classifier):
    """Detection by the mechanical filters and by the verifier, per error type, on reviewed mutations and faithful
    paraphrase controls; aggregates only go to the report."""
    rows = [json.loads(line) for line in CHALLENGES.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = {}
    for row in rows:
        mech = bool(mechanical(row["source"], row["rewrite"], classifier))
        ver = bool(verify(calls, row["source"], row["rewrite"]))
        results.setdefault(row["kind"], []).append((mech, ver))
    return results, len(rows)


def challenge_report(results, total, made):
    lines = ["## Challenge set", "",
             f"Measured {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}: {total} reviewed cases in `eval/rewording-challenges.jsonl`, "
             f"{made} verifier calls to `{understanding.DEFAULT_MODEL}`. A mutation is caught when a check flags it; a faithful control is wrongly "
             "rejected when a check flags it. The verifier is the same model as the writer, so its catches are correlated with the writer's "
             "blind spots. Checks are filters, not proof.", "",
             "| Case kind | Cases | Mechanical filters flag | Verifier flags | Either flags |", "|---|---|---|---|---|"]
    for kind in sorted(results):
        rows = results[kind]
        n = len(rows)
        lines.append(f"| {kind} | {n} | {sum(m for m, _ in rows)}/{n} | {sum(v for _, v in rows)}/{n} | {sum(m or v for m, v in rows)}/{n} |")
    return "\n".join(lines) + "\n"


def review_page():
    cards = []
    for path in sorted(OUT.glob("*--*.json")):
        c = json.loads(path.read_text(encoding="utf-8"))
        e = html.escape
        rows = "".join(f"<tr><td>{e(p['source'])}</td><td>{e(p['rewrite'])}</td><td>{e(', '.join(p['failures']) or 'ok')}</td></tr>" for p in c["passages"])
        cards.append(f"<section><h2>{e(c['subject'])} · {e(c['intent'])}</h2><p>Checks: <b>{'passed' if c['checks_passed'] else 'flagged'}</b>"
                     f" (field: {e(', '.join(c['field_failures']) or 'ok')})</p><table><tr><th>Original</th><th>Reworded</th><th>Filters</th></tr>{rows}</table>"
                     f"<p class='id'>input_sha256 {e(c['input_sha256'])}<br>output_sha256 {e(c['output_sha256'])}<br>format_identity {e(c['format_identity'])}</p></section>")
    page = ("<!doctype html><meta charset='utf-8'><title>Rewording review</title><style>body{font-family:sans-serif;max-width:1100px;margin:auto;padding:16px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}.id{font:12px monospace;color:#555}</style>"
            "<h1>Rewording review (local, not published)</h1><p>Approve a field only if every reworded passage says exactly what the original says. "
            "Copy the three identities of each approved field into decisions.json.</p>" + "".join(cards))
    (OUT / "review.html").write_text(page, encoding="utf-8")
    return OUT / "review.html"


def approve(decisions_path, store=answer_searcher.REWORDINGS_PATH):
    """Publish only candidates the owner approved by their exact identities, unchanged since review, with passing checks."""
    decisions = json.loads(Path(decisions_path).read_text(encoding="utf-8")).get("approved", [])
    entries = []
    for decision in decisions:
        path = OUT / f"{decision['subject'].replace(' ', '_')}--{decision['intent']}.json"
        c = json.loads(path.read_text(encoding="utf-8"))
        unchanged = (c["input_sha256"] == decision["input_sha256"] and c["output_sha256"] == decision["output_sha256"]
                     and answer_searcher.sections_digest(c["sections"]) == c["output_sha256"]
                     and c["format_identity"] == decision["format_identity"] == text_format.FORMAT_IDENTITY)
        if not unchanged or not c["checks_passed"]:
            raise SystemExit(f"Refused {decision['subject']} / {decision['intent']}: changed since review, other formatter, or failed checks")
        entries.append({"subject": c["subject"], "intent": c["intent"], "status": "approved", "input_sha256": c["input_sha256"],
                        "format_identity": c["format_identity"], "sections": c["sections"], "output_sha256": c["output_sha256"],
                        "model": c["model"], "reword_prompt_sha256": c["reword_prompt_sha256"],
                        "verify_prompt_sha256": c["verify_prompt_sha256"], "approved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    document = json.loads(Path(store).read_text(encoding="utf-8"))
    document["entries"] = entries
    partial = Path(store).with_suffix(".json.part")
    partial.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    partial.replace(store)
    return len(entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inventory", action="store_true")
    group.add_argument("--challenge", action="store_true")
    group.add_argument("--generate", action="store_true")
    group.add_argument("--review", action="store_true")
    group.add_argument("--approve", metavar="DECISIONS")
    parser.add_argument("--max-calls", type=int, default=300, help="stop before making more cloud calls than this")
    args = parser.parse_args(argv)
    if args.review:
        print(review_page())
        return 0
    if args.approve:
        print(f"Published {approve(args.approve)} approved entries")
        return 0
    values = field_values(builder.load_dataset())
    if args.inventory:
        print("\n".join(inventory(values)))
        return 0
    classifier, calls = QuestionClassifier(), Calls(args.max_calls)
    started = time.perf_counter()
    if args.challenge:
        results, total = challenge(calls, classifier)
        section = challenge_report(results, total, calls.made)
        text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else "# Rewording pilot (D-029)\n"
        REPORT.write_text(text.split("\n## Challenge set")[0].rstrip("\n") + "\n\n" + section, encoding="utf-8")
        print(section)
    else:
        generate(values, calls, classifier)
    print(f"{calls.made} cloud calls in {time.perf_counter() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
