"""Readable structure for long graph text (D-028): sections and numbered points, found in the text itself.

Deterministic and conservative: the only changes are removing the numbering markers that start each point,
trimming whitespace and capitalising first letters. Every letter of the stored text survives, in order, so no fact
can be added, dropped or reworded here. Text without a clear numbered run is left as one paragraph.
"""
import re

# "1." "2," "3、" or "(1)" "（2）", at the start or after whitespace or a colon, then whitespace. A bare "1 pig" is
# not a marker: plain numbers are too common in the text to split on.
MARKER = re.compile(r"(?:^|(?<=[\s:;]))(?:[(（](\d{1,2})[)）]|(\d{1,2})[.,、])(?=\s)")
MAX_HEADING = 80


def markers(text):
    found = []
    for match in MARKER.finditer(text):
        paren, plain = match.group(1), match.group(2)
        found.append({"start": match.start(), "end": match.end(), "n": int(paren or plain), "style": "paren" if paren else "plain"})
    return found


def runs(text):
    """Numbered runs counting up from 1 in one marker style, at least two points long, not inside another run."""
    found, accepted, covered_until = markers(text), [], -1
    for i, first in enumerate(found):
        if first["n"] != 1 or first["start"] <= covered_until:
            continue
        run = [first]
        for later in found[i + 1:]:
            if later["style"] != first["style"]:
                continue
            if later["n"] == run[-1]["n"] + 1:
                run.append(later)
            elif later["n"] == 1:
                break   # a new list starts: "health education: 1. ..." is not point 5 of the list before
        if len(run) >= 2:
            accepted.append(run)
            covered_until = run[-1]["start"]
    return accepted


def capitalised(text):
    text = " ".join(text.split())
    return text[:1].upper() + text[1:]


def split_heading(text):
    """(text before, heading) when text ends with a short labelled clause such as "health education:"."""
    stripped = text.rstrip()
    if not stripped.endswith((":", "：")):
        return text, None
    body = stripped[:-1]
    cut = max(body.rfind(". "), body.rfind("; "))
    heading = body[cut + 2:] if cut >= 0 else body
    if not heading.strip() or len(heading) > MAX_HEADING:
        return text, None
    return (body[:cut + 1] if cut >= 0 else ""), heading


def sections(text):
    """[{heading, paragraph, items}] in text order, or None when there is no numbered run to show."""
    found = runs(text)
    if not found:
        return None
    result, cursor, previous_items = [], 0, None
    for run in found:
        before, heading = split_heading(text[cursor:run[0]["start"]])
        if before.strip():
            if previous_items is not None:
                previous_items[-1] += " " + before   # the rest of the last point of the run before
            else:
                result.append({"heading": None, "paragraph": capitalised(before), "items": []})
        items = [text[a["end"]:b["start"]] for a, b in zip(run, run[1:])] + [""]
        section = {"heading": capitalised(heading) if heading else None, "paragraph": None, "items": items}
        result.append(section)
        previous_items, cursor = items, run[-1]["end"]
    previous_items[-1] += text[cursor:]
    for section in result:
        section["items"] = [capitalised(item) for item in section["items"] if item.strip()]
    return result
