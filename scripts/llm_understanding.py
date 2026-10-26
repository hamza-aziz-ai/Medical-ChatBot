"""Step-3 experiment (D-026): score routing frames on the synthetic understanding set.

Offline only: nothing here is imported by the API, run in CI against a model, or used to answer anyone. The protocol
and the bar are fixed in docs/pilot/LLM-UNDERSTANDING.md; this script never changes them.

    python scripts/llm_understanding.py --rules        # score the current rules (the baseline)
    python scripts/llm_understanding.py --model --dev  # one run on the dev split, for prompt work; not reported
    python scripts/llm_understanding.py --model        # three runs on the whole set with the frozen prompt

Per-turn frames go to pilot-data/understanding/ (git-ignored); the report's Results section gets aggregates only.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import answer_searcher  # noqa: E402
import chatbot_graph_logic  # noqa: E402
import understanding  # noqa: E402
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


# The model (D-026): the contract (prompt, candidates, validator, transport) lives in api/understanding.py, shared
# with the running API (D-027), so the experiment and the runtime can never drift apart.

MODEL = understanding.DEFAULT_MODEL
OLLAMA_URL = understanding.DEFAULT_URL
OPTIONS, THINK = understanding.OPTIONS, understanding.THINK
TIMEOUT_SECONDS = understanding.TIMEOUT_SECONDS
UNSUPPORTED = understanding.UNSUPPORTED
SYSTEM_PROMPT = understanding.SYSTEM_PROMPT
ModelError = understanding.ModelError
prompt_digest = understanding.prompt_digest
validate = understanding.validate
RUNS = 3


def ollama_chat(messages):
    return understanding.chat(messages, OLLAMA_URL, MODEL)


def candidates_for(bot, question, topic, selections):
    """The candidates respond() would give the model (D-027): mentions typed as the rules type them, or the topic
    alone when the full follow-up check passes and nothing else is named."""
    topic = bot.valid_topic(topic)
    alias_hits = []
    arguments = bot.classifier.check_medical(question.lower(), alias_hits)
    from_topic = False
    if not arguments and topic and bot.is_follow_up(question):
        arguments, from_topic = {topic["name"]: [topic["type"]]}, True
    chosen = bot.valid_selections(selections, arguments)
    for name in arguments:
        if name in chosen:
            arguments[name] = [chosen[name]]
        elif topic and name == topic["name"] and topic["type"] in arguments[name]:
            arguments[name] = [topic["type"]]
    return understanding.build_candidates(arguments, from_topic), any(len(hit["names"]) > 1 for hit in alias_hits)


def model_frame(decision, checked, candidates, topic):
    if decision == "answer":
        pairs = sorted({(intent, c["name"]) for intent, c in checked})
        subjects = sorted({(c["name"], c["type"]) for _, c in checked})
        topic_out = {"name": subjects[0][0], "type": subjects[0][1]} if len(subjects) == 1 else None
        return {"decision": "answer", "entities": [{"name": n, "type": t} for n, t in subjects],
                "intents": [list(p) for p in pairs], "topic_out": topic_out}
    topic_out = topic
    if decision == "unsupported":
        # As the labels say: the one known subject the turn names, else the topic before.
        named = {c["name"] for c in candidates if c["source"] == "mention"}
        if len(named) == 1:
            name = named.pop()
            types = {c["type"] for c in candidates if c["name"] == name} & ({c["type"] for _, c in checked} or set(TYPES))
            if len(types) == 1:
                topic_out = {"name": name, "type": types.pop()}
    return {"decision": decision, "entities": [], "intents": [], "topic_out": topic_out}


def ask_model(bot, question, topic, selections, chat=None):
    """{"frame" or None, "error", "seconds"}: one call, a 2 s limit counted as a failure, no retry."""
    candidates, ambiguous_alias = candidates_for(bot, question, topic, selections)
    message = {"question": question, "candidates": candidates}
    started = time.perf_counter()
    try:
        content, _ = (chat or ollama_chat)([{"role": "system", "content": SYSTEM_PROMPT},
                                            {"role": "user", "content": json.dumps(message, ensure_ascii=False)}])
        seconds = time.perf_counter() - started
        if seconds > TIMEOUT_SECONDS:
            raise ModelError("timeout")
        decision, checked = validate(content, candidates, ambiguous_alias)
        return {"frame": model_frame(decision, checked, candidates, bot.valid_topic(topic)), "error": None, "seconds": seconds}
    except (ModelError, OSError, ValueError, KeyError, TypeError) as error:
        name = str(error) if isinstance(error, ModelError) else ("timeout" if "timed out" in str(error) else type(error).__name__)
        return {"frame": None, "error": name, "seconds": time.perf_counter() - started}


def invalid_frame(topic):
    return {"decision": "invalid", "entities": [], "intents": [], "topic_out": topic}


CONFIGURATIONS = ("validated model", "model plus fallback", "rules-first")


def configured(name, rules, model, topic):
    """One configuration's frame from the rules' frame and the model's result for the same input."""
    if name == "validated model":
        return model["frame"] or invalid_frame(topic)
    if name == "model plus fallback":
        return model["frame"] or rules
    # rules-first: only a no_entity abstention goes to the model; every other rule result stands.
    return (model["frame"] or rules) if rules["reason"] == "no_entity" else rules


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


def run_model(cases, bot, runs=RUNS, chat=None):
    """Score every configuration in each run. Within a run each distinct input is asked once and shared by the
    configurations; across runs nothing is cached, so stability is measured, not assumed."""
    config_runs = {name: [] for name in CONFIGURATIONS}
    calls = []
    for run in range(runs):
        cache = {}

        def both(question, topic, selections, run=run, cache=cache):
            key = (question, json.dumps(topic, sort_keys=True), json.dumps(selections, sort_keys=True))
            if key not in cache:
                rules = rules_frame(bot, question, topic, selections)
                model = ask_model(bot, question, topic, selections, chat)
                calls.append({"run": run, "error": model["error"], "seconds": model["seconds"],
                              "no_entity": rules["reason"] == "no_entity"})
                cache[key] = (rules, model)
            return cache[key]

        for name in CONFIGURATIONS:
            config_runs[name].append(score(cases, lambda q, t, s, name=name: configured(name, *both(q, t, s), t)))
    return config_runs, calls


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0.0


def agreement(runs_rows):
    """Share of held-out isolated turns whose normalised frame is the same in every run."""
    frames = {}
    for rows in runs_rows:
        for r in rows:
            if r["mode"] == "isolated" and r["split"] == "test":
                got = r["got"]
                frames.setdefault((r["id"], r["turn"]), []).append(json.dumps(normalise(got) if got["decision"] != "invalid" else "invalid"))
    same = sum(len(set(v)) == 1 for v in frames.values())
    return same, len(frames)


def evaluate(rule_rows, config_runs, calls):
    """The pre-registered bar, per configuration; quality uses the worst of the runs."""
    rules = summary(rule_rows)["isolated"]["win_categories"]
    rule_share = rules["correct"] / rules["turns"]
    rules_unsafe = {(r["id"], r["turn"], r["mode"]) for r in rule_rows if r["unsafe"]}
    valid = sum(c["error"] is None for c in calls)
    seconds = [c["seconds"] for c in calls]
    reliability = {"calls": len(calls), "valid": valid, "errors": {}, "p50": percentile(seconds, 0.5), "p95": percentile(seconds, 0.95),
                   "timeouts": sum(c["error"] == "timeout" for c in calls),
                   "rules_first_share": sum(c["no_entity"] for c in calls) / len(calls) if calls else 0.0}
    for c in calls:
        if c["error"]:
            reliability["errors"][c["error"]] = reliability["errors"].get(c["error"], 0) + 1
    out = {}
    for name, runs_rows in config_runs.items():
        held = [[r for r in rows if r["split"] == "test"] for rows in runs_rows]
        new_unsafe = sum(r["unsafe"] and (r["id"], r["turn"], r["mode"]) not in rules_unsafe for rows in held for r in rows)
        subset_unsafe = sum(r["unsafe"] and r["safety"] for rows in held for r in rows)
        summaries = [summary(rows) for rows in runs_rows]
        shares = [s["isolated"]["win_categories"]["correct"] / s["isolated"]["win_categories"]["turns"] for s in summaries]
        same, turns = agreement(runs_rows)
        model_based = name != "rules-first" or reliability["rules_first_share"] > 0
        out[name] = {
            "summaries": summaries, "new_unsafe": new_unsafe, "subset_unsafe": subset_unsafe,
            "gain_points": 100 * (min(shares) - rule_share), "agreement": [same, turns],
            "gates": {
                "safety": new_unsafe == 0 and subset_unsafe == 0,
                "quality": 100 * (min(shares) - rule_share) >= 10,
                "reliability": (not model_based) or (valid >= 0.99 * len(calls) and same >= 0.99 * turns),
                "latency": (not model_based) or (reliability["p95"] <= 1.0),
            },
        }
    return out, reliability


def model_section(run):
    r, lines = run["reliability"], []
    lines += [f"### Model: `{run['model']}`", "",
              f"Scored {run['measured_at']} at commit `{run['commit'][:12]}`: set SHA-256 `{run['set_sha256'][:16]}…`, prompt SHA-256 "
              f"`{run['prompt_sha256'][:16]}…`, script SHA-256 `{run['script_sha256'][:16]}…`; {run['runs']} runs; Ollama {run['ollama_version']}, "
              f"which reported the model as `{run['reported_model']}`; options `{json.dumps(run['options'])}`, think `{run['think']}`. "
              "A cloud model can change under the same name, so these numbers hold only for this run.", "",
              "| Configuration | Held-out complete frames (isolated, each run) | Paraphrase and multi-turn (each run) | Change vs rules, worst run | "
              "Held-out, full conversations (each run) | New wrong-subject answers vs rules (all runs) | Wrong-subject answers, safety subset (all runs) |",
              "|---|---|---|---|---|---|---|"]
    for name in CONFIGURATIONS:
        c = run["configurations"][name]
        each = lambda key, mode="isolated": ", ".join(pct(s[mode][key]["correct"], s[mode][key]["turns"]) for s in c["summaries"])  # noqa: E731
        lines.append(f"| {name} | {each('held_out')} | {each('win_categories')} | {c['gain_points']:+.1f} points | "
                     f"{each('held_out', 'rollout')} | {c['new_unsafe']} | {c['subset_unsafe']} |")
    errors = ", ".join(f"{k} {v}" for k, v in sorted(r["errors"].items())) or "none"
    same, turns = run["configurations"]["validated model"]["agreement"]
    lines += ["", f"Model calls: {r['calls']}, valid {pct(r['valid'], r['calls'])}; failures: {errors}. Identical validated frames across runs: "
              f"{pct(same, turns)} of held-out turns. Latency p50 {r['p50']:.2f} s, p95 {r['p95']:.2f} s, {r['timeouts']} over the "
              f"{TIMEOUT_SECONDS:.0f} s limit. Rules-first would call the model on {100 * r['rules_first_share']:.1f}% of inputs.", "",
              "| Configuration | Safety | Quality (≥ 10 points) | Reliability (≥ 99% valid and identical) | Latency (p95 ≤ 1 s) |", "|---|---|---|---|---|"]
    mark = lambda ok: "pass" if ok else "fail"  # noqa: E731
    for name in CONFIGURATIONS:
        g = run["configurations"][name]["gates"]
        lines.append(f"| {name} | {mark(g['safety'])} | {mark(g['quality'])} | {mark(g['reliability'])} | {mark(g['latency'])} |")
    lines += ["", "| Category (held out, isolated, each run) | " + " | ".join(CONFIGURATIONS) + " |", "|---|" + "---|" * len(CONFIGURATIONS)]
    for category in CATEGORIES:
        cells = [", ".join(pct(s["isolated"]["by_category"][category]["correct"], s["isolated"]["by_category"][category]["turns"])
                           for s in run["configurations"][name]["summaries"]) for name in CONFIGURATIONS]
        lines.append(f"| {category} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def results_section(runs):
    lines = [RESULTS_HEADING, ""]
    for name, run in runs.items():
        if "configurations" in run:
            lines += model_section(run)
            continue
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


def ollama_get(path):
    try:
        with urllib.request.urlopen(OLLAMA_URL + path, timeout=5) as response:
            return json.loads(response.read(MAX_REPLY_BYTES))
    except (OSError, ValueError):
        return {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules", action="store_true", help="score the current rules")
    parser.add_argument("--model", action="store_true", help=f"score {MODEL} through the local Ollama")
    parser.add_argument("--dev", action="store_true", help="with --model: one run on the dev split only, not reported")
    args = parser.parse_args(argv)
    if args.rules == args.model:
        parser.error("choose one: --rules or --model")
    try:
        cases = load_set()
        check_set(cases, read_dictionary())
    except (OSError, ValueError, KeyError, SetError) as error:
        print(f"Understanding set rejected: {error}", file=sys.stderr)
        return 1
    bot = rules_bot()
    rule_rows = score(cases, lambda question, topic, selections: rules_frame(bot, question, topic, selections))
    base = {"measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit(),
            "set_sha256": set_digest(), "scenarios": len(cases)}
    OUT.mkdir(parents=True, exist_ok=True)
    if args.rules:
        (OUT / "rules-frames.json").write_text(json.dumps(rule_rows, indent=1), encoding="utf-8")
        write_report("Rules (baseline)", {**base, "summary": summary(rule_rows)})
        held = summary(rule_rows)["isolated"]["held_out"]
        print(f"Rules: {held['correct']}/{held['turns']} held-out turns correct, {held['unsafe']} unsafe (isolated)")
        return 0
    if args.dev:
        # Prompt work may look only at dev cases; the held-out split is scored once per frozen prompt.
        dev = [c for c in cases if c["split"] == "dev"]
        config_runs, calls = run_model(dev, bot, runs=1)
        rows = config_runs["validated model"][0]
        (OUT / "dev-frames.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        valid = sum(c["error"] is None for c in calls)
        print(f"Dev: {sum(r['correct'] for r in rows)}/{len(rows)} turns correct, {sum(r['unsafe'] for r in rows)} unsafe, "
              f"{valid}/{len(calls)} valid, p95 {percentile([c['seconds'] for c in calls], 0.95):.2f} s")
        return 0
    probe = ollama_chat([{"role": "user", "content": "Reply with the single word: ok"}])
    config_runs, calls = run_model(cases, bot)
    configurations, reliability = evaluate(rule_rows, config_runs, calls)
    run = {**base, "model": MODEL, "reported_model": probe[1], "ollama_version": ollama_get("/api/version").get("version", "unknown"),
           "options": OPTIONS, "think": THINK, "runs": RUNS, "prompt_sha256": prompt_digest(),
           "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "configurations": configurations, "reliability": reliability}
    (OUT / "model-frames.json").write_text(json.dumps({"calls": calls, "runs": config_runs}, indent=1), encoding="utf-8")
    write_report(f"Model: {MODEL}", run)
    for name in CONFIGURATIONS:
        print(name, run["configurations"][name]["gates"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
