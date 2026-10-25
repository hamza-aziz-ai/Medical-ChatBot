import ast
import json
import re
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "question-pairs.ipynb"


def load_cells():
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def helper():
    for cell in load_cells():
        source = "".join(cell["source"])
        if cell["cell_type"] != "code" or "def convert_text_to_index_array" not in source:
            continue
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name == "convert_text_to_index_array":
                namespace = {"text_to_word_sequence": str.split}
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
                return namespace["convert_text_to_index_array"]
    raise AssertionError("helper not found")


def test_helper_keeps_known_tokens_and_skips_unknown_ones():
    convert = helper()
    assert convert("a b c", {"a": 1, "c": 3}) == [1, 3]
    assert convert("", {"a": 1}) == []
    assert convert("x y", {"a": 1}) == []


def test_export_path_and_notice():
    cells = load_cells()
    text = "".join("".join(cell["source"]) for cell in cells)
    assert not re.search(r"app[\\/]+models", text)
    assert "../api/models/dictionary.json" in text
    assert cells[0]["cell_type"] == "markdown" and "not re-run" in "".join(cells[0]["source"])
