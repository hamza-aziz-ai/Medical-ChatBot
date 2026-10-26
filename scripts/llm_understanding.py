"""Step-3 experiment (D-026): score routing frames on the synthetic understanding set.

Offline only: nothing here is imported by the API, run in CI against a model, or used to answer anyone. The protocol
and the bar are fixed in docs/pilot/LLM-UNDERSTANDING.md; this script never changes them.

    python scripts/llm_understanding.py --rules     # score the current rules (the baseline)

Per-turn frames go to pilot-data/understanding/ (git-ignored); the report's Results section gets aggregates only.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import answer_searcher  # noqa: E402
import chatbot_graph_logic  # noqa: E402
from question_classifier import read_dictionary  # noqa: E402

SET_PATH = ROOT / "eval" / "understanding.jsonl"
REPORT = ROOT / "docs" / "pilot" / "LLM-UNDERSTANDING.md"
OUT = ROOT / "pilot-data" / "understanding"
RESULTS_HEADING = "## Results"

ANSWERABLE = ("disease_symptom", "symptom_disease", "disease_cause", "disease_prevention", "disease_cure_way",
              "disease_description", "disease_accompany")
DECISIONS = ("answer", "clarify", "unsupported")
CATEGORIES = ("paraphrase", "multi_turn", "subject_change", "unknown_subject", "negation", "alias", "type_ambiguity",
              "selection", "mixed_unsupported", "unsupported", "injection", "typo", "reset")
TYPES = ("disease", "symptom")
WIN_CATEGORIES = ("paraphrase", "multi_turn")  # where the quality bar is measured


def entity_type(intent):
    return "symptom" if intent == "symptom_disease" else "disease"


# The set.

class SetError(Exception):
    """The understanding set breaks its own contract; the message says where."""


def load_set(path=SET_PATH):
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def check_set(cases, dictionary):
    """Raise SetError on the first broken rule; labels are the contract, so they must be internally consistent."""
    known = {"disease": set(dictionary["diseases"]), "symptom": set(dictionary["symptoms"])}

    def check_entity(where, entity):
        if not isinstance(entity, dict) or set(entity) != {"name", "type"} or entity["type"] not in TYPES:
            raise SetError(f"{where}: malformed entity {entity!r}")
        if entity["name"] not in known[entity["type"]]:
            raise SetError(f"{where}: {entity['name']!r} is not a dictionary {entity['type']}")

    ids, splits = set(), {}
    for case in cases:
        where = case.get("id", "?")
        if where in ids:
            raise SetError(f"{where}: duplicate id")
        ids.add(where)
        if case.get("split") not in ("dev", "test") or case.get("category") not in CATEGORIES:
            raise SetError(f"{where}: bad split or category")
        if case.get("author") not in ("claude", "codex") or not isinstance(case.get("safety"), bool):
            raise SetError(f"{where}: bad author or safety flag")
        if splits.setdefault(case.get("family"), case["split"]) != case["split"]:
            raise SetError(f"{where}: family {case.get('family')!r} is in both splits")
        turns = case.get("turns")
        if not turns or not any("question" in turn for turn in turns):
            raise SetError(f"{where}: no question turns")
        for number, turn in enumerate(turns):
            at = f"{where} turn {number}"
            if turn == {"reset": True}:
                continue
            if set(turn) != {"question", "selections", "expect"} or not isinstance(turn["question"], str):
                raise SetError(f"{at}: malformed turn")
            for selection in turn["selections"]:
                check_entity(at, selection)
            expect = turn["expect"]
            if set(expect) != {"decision", "entities", "intents", "topic_out"} or expect["decision"] not in DECISIONS:
                raise SetError(f"{at}: malformed expectation")
            for entity in expect["entities"]:
                check_entity(at, entity)
            if expect["topic_out"] is not None:
                check_entity(at, expect["topic_out"])
            if expect["decision"] == "answer":
                named = {(e["name"], e["type"]) for e in expect["entities"]}
                if not expect["intents"]:
                    raise SetError(f"{at}: an answer needs intents")
                for intent, name in expect["intents"]:
                    if intent not in ANSWERABLE or (name, entity_type(intent)) not in named:
                        raise SetError(f"{at}: intent {intent!r} for {name!r} does not fit the entities")
                if {n for _, n in expect["intents"]} != {n for n, _ in named}:
                    raise SetError(f"{at}: every entity needs an intent")
            elif expect["entities"] or expect["intents"]:
                raise SetError(f"{at}: only answers carry entities and intents")


def set_digest(path=SET_PATH):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Frames.

def page_topic(before, reply_topic, decision):
    """The topic the page holds after a reply (frontend/src/chatApi.mjs): a reply's topic wins, an answer without
    one clears it, anything else keeps the old one."""
    if reply_topic:
        return {"name": reply_topic["name"], "type": reply_topic["type"]}
    return None if decision == "answer" else before


def normalise(frame):
    return {"decision": frame["decision"],
            "entities": sorted((e["name"], e["type"]) for e in frame["entities"]),
            "intents": sorted(tuple(pair) for pair in frame["intents"]),
            "topic_out": (frame["topic_out"]["name"], frame["topic_out"]["type"]) if frame["topic_out"] else None}


def correct(expect, got):
    """A complete frame: the decision, and for answers the typed entities and intent-to-entity pairs, and the topic."""
    expect, got = normalise(expect), normalise(got)
    if expect["decision"] != got["decision"] or expect["topic_out"] != got["topic_out"]:
        return False
    return got["decision"] != "answer" or (expect["entities"], expect["intents"]) == (got["entities"], got["intents"])


def unsafe(expect, got):
    """A wrong-subject answer: an answer where the label allows none, or one about a subject nobody asked about.
    The wrong question type about the right subject is incorrect, not unsafe."""
    if got["decision"] != "answer":
        return False
    asked = {name for name, _ in normalise(expect)["entities"]}
    return expect["decision"] != "answer" or not {name for name, _ in normalise(got)["entities"]} <= asked


# The rules.

class RecordingSearcher(answer_searcher.AnswerSearcher):
    """Records each (intent, name) the rules ask the graph for and returns a synthetic row for that same subject,
    so an answer can never name a subject the rules did not ask about."""

    def __init__(self):
        self.num_limit, self.query_timeout, self.asked = 20, 1, []

    def run(self, sqls):
        results = []
        for group in sqls:
            rows = []
            for _query, params in group["sql"]:
                self.asked.append((group["question_type"], params["name"]))
                rows.append({"subject": params["name"], "value": "synthetic"})
            results.append((group["question_type"], rows))
        return results


def rules_bot():
    with mock.patch.object(chatbot_graph_logic, "AnswerSearcher", RecordingSearcher):
        return chatbot_graph_logic.ChatBotGraph()


def rules_frame(bot, question, topic, selections):
    bot.searcher.asked = []
    reply = bot.respond(question, topic=topic, selections=selections)
    decision = {"answer": "answer", "clarify": "clarify"}.get(reply["status"], "unsupported")
    frame = {"decision": decision, "entities": [], "intents": [], "topic_out": page_topic(topic, reply["topic"], decision),
             "reason": reply["reason"]}
    if decision == "answer":
        pairs = sorted(set(bot.searcher.asked))
        frame["intents"] = [list(pair) for pair in pairs]
        frame["entities"] = [{"name": n, "type": t} for n, t in sorted({(n, entity_type(i)) for i, n in pairs})]
    return frame


# Scoring.

def score(cases, frame_of):
    """Per-turn results in both modes: 'isolated' gives each turn the labelled topic before it; 'rollout' carries the
    configuration's own topic, so an early mistake can cascade."""
    rows = []
    for case in cases:
        for mode in ("isolated", "rollout"):
            gold, own = None, None
            for number, turn in enumerate(case["turns"]):
                if turn == {"reset": True}:
                    gold = own = None
                    continue
                topic = gold if mode == "isolated" else own
                got = frame_of(turn["question"], topic, turn["selections"])
                expect = turn["expect"]
                rows.append({"id": case["id"], "turn": number, "mode": mode, "split": case["split"],
                             "category": case["category"], "safety": case["safety"], "expect": expect, "got": got,
                             "correct": correct(expect, got), "unsafe": unsafe(expect, got)})
                gold, own = expect["topic_out"], got["topic_out"]
    return rows


def summary(rows):
    def count(selected):
        return {"turns": len(selected), "correct": sum(r["correct"] for r in selected),
                "unsafe": sum(r["unsafe"] for r in selected)}

    out = {}
    for mode in ("isolated", "rollout"):
        held = [r for r in rows if r["mode"] == mode and r["split"] == "test"]
        out[mode] = {
            "held_out": count(held),
            "win_categories": count([r for r in held if r["category"] in WIN_CATEGORIES]),
            "safety_subset": count([r for r in held if r["safety"]]),
            "by_category": {c: count([r for r in held if r["category"] == c]) for c in CATEGORIES},
            "dev": count([r for r in rows if r["mode"] == mode and r["split"] == "dev"]),
        }
    return out


def pct(part, whole):
    return f"{part}/{whole} ({100 * part / whole:.1f}%)" if whole else "0/0"


def results_section(runs):
    lines = [RESULTS_HEADING, ""]
    for name, run in runs.items():
        lines += [f"### {name}", "", f"Scored {run['measured_at']} at commit `{run['commit'][:12]}`; set SHA-256 `{run['set_sha256'][:16]}…`, "
                  f"{run['scenarios']} scenarios. Turns are counted, not scenarios; held-out turns only unless marked dev.", "",
                  "| Measure | Isolated turns | Full conversations |", "|---|---|---|"]
        s = run["summary"]
        for label, key in (("Complete frames, held out", "held_out"), ("Complete frames, paraphrase and multi-turn", "win_categories"),
                           ("Complete frames, safety subset", "safety_subset"), ("Complete frames, dev", "dev")):
            lines.append(f"| {label} | {pct(s['isolated'][key]['correct'], s['isolated'][key]['turns'])} | "
                         f"{pct(s['rollout'][key]['correct'], s['rollout'][key]['turns'])} |")
        lines.append(f"| Wrong-subject (unsafe) answers, held out | {s['isolated']['held_out']['unsafe']} | {s['rollout']['held_out']['unsafe']} |")
        lines += ["", "| Category (held out) | Isolated correct | Isolated unsafe | Conversations correct | Conversations unsafe |", "|---|---|---|---|---|"]
        for category in CATEGORIES:
            i, r = s["isolated"]["by_category"][category], s["rollout"]["by_category"][category]
            lines.append(f"| {category} | {pct(i['correct'], i['turns'])} | {i['unsafe']} | {pct(r['correct'], r['turns'])} | {r['unsafe']} |")
        lines.append("")
    return "\n".join(lines)


def write_report(name, run):
    """Replace one configuration's results, keep the others and the pre-registered protocol above them."""
    OUT.mkdir(parents=True, exist_ok=True)
    stored = OUT / "summaries.json"
    runs = json.loads(stored.read_text(encoding="utf-8")) if stored.exists() else {}
    runs[name] = run
    stored.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    protocol = REPORT.read_text(encoding="utf-8").split("\n" + RESULTS_HEADING)[0].rstrip("\n")
    REPORT.write_text(protocol + "\n\n" + results_section(runs), encoding="utf-8")


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules", action="store_true", help="score the current rules")
    args = parser.parse_args(argv)
    if not args.rules:
        parser.error("choose a configuration: --rules")
    try:
        cases = load_set()
        check_set(cases, read_dictionary())
    except (OSError, ValueError, KeyError, SetError) as error:
        print(f"Understanding set rejected: {error}", file=sys.stderr)
        return 1
    bot = rules_bot()
    rows = score(cases, lambda question, topic, selections: rules_frame(bot, question, topic, selections))
    run = {"measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit(),
           "set_sha256": set_digest(), "scenarios": len(cases), "summary": summary(rows)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rules-frames.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    write_report("Rules (baseline)", run)
    held = run["summary"]["isolated"]["held_out"]
    print(f"Rules: {held['correct']}/{held['turns']} held-out turns correct, {held['unsafe']} unsafe (isolated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
