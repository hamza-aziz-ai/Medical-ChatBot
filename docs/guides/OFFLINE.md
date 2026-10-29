# Offline scripts and experiments

Scripts and notebooks that never run in the API. Back to the [README](../../README.md).

## Language-model evaluation and rewording

These scripts call the cloud model through your local Ollama; they never run in CI and never touch the running API.

```
python scripts/llm_understanding.py --round2 --dry-run   # check the frozen Round-2 inputs; no model calls
python scripts/reword_answers.py --inventory             # sizes of the rewording pilot fields; no model calls
python scripts/reword_answers.py --challenge             # measure the rewording checks on reviewed broken rewrites
python scripts/reword_answers.py --generate              # reword the pilot fields into local candidates
python scripts/reword_answers.py --review                # write pilot-data/rewordings/review.html for the owner
python scripts/reword_answers.py --approve decisions.json   # publish only approved, unchanged, passing fields
```

Results: [docs/pilot/LLM-UNDERSTANDING.md](../pilot/LLM-UNDERSTANDING.md) (Rounds 1 and 2) and [docs/pilot/REWORDING.md](../pilot/REWORDING.md).

## Historical training experiments

The notebooks and model assets remain historical experiments. Their dependencies, including Keras and TensorFlow, are not supplied by the runtime requirements; use a separate environment.

The training notebooks expect the Quora Question Pairs data at `notebooks/data/train.csv`. It is not committed; download it from Kaggle (requires a Kaggle API token and accepting the competition rules):

```
kaggle competitions download -c quora-question-pairs -p notebooks/data
```

Unzip the download so that `notebooks/data/train.csv` exists.
